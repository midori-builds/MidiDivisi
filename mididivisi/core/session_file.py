"""
Session save/load.

A .mididivisi file is a zip containing:
  - manifest.json          - format version, save timestamp, original filename
  - score.musicxml         - a full copy of the original score at save time
  - session.json           - the session's structure, keyed by natural
                              keys (NOT .id, which is a fresh random
                              UUID every parse - see session.py's
                              Track.natural_key / InstrumentIdentity.natural_key).
                              Also stores Profile assignment per
                              instrument and InventoryItem assignment
                              per group, keyed by their real .id (a
                              Profile is a persistent, separately-
                              editable resource, not something re-
                              derived by re-parsing - so it's resolved
                              against the LIVE ProfileLibrary on load,
                              not embedded/frozen, meaning a reload
                              reflects the profile's CURRENT state,
                              same philosophy as natural-key track
                              resolution).
  - settings_snapshot.json - Settings' state at save time

Packaging the score alongside the session (rather than just storing a
path to the original file) means load never needs a "locate the
missing file" fallback - the score always travels with the session.

Loading is a two-step process because of the settings-snapshot
comparison: start_loading_session() opens the file and compares the
embedded settings against the LIVE settings, WITHOUT yet parsing the
score or picking a settings source (the UI layer needs to prompt the
user first if they differ, before either becomes the active choice -
see main_window.py). finish_loading_session() completes the load once
that choice is known.

Reconstruction on load is DIRECT (building Instrument/Group objects
straight from the saved structure) rather than by replaying the saved
merges through Session.merge_groups/merge_instruments. This is
deliberate: merge_instruments auto-matches groups by label as a side
effect, which could produce a DIFFERENT final structure than what was
actually saved if the user had done more specific manual merging or
splitting afterward. Direct reconstruction guarantees an exact match
to the saved state instead.

The extracted temp score (SessionLoadResult.temp_score_path) is
deliberately NOT auto-deleted after finish_loading_session - the
caller (MainWindow) keeps using that path as "the current score" for
the rest of the session, e.g. if the user then does Save Session
again, that's what gets re-embedded. Left for the OS's normal temp-
file cleanup rather than managed explicitly - a reasonable
simplification rather than adding a full copy-to-a-managed-location
step for what's a fairly rare operation.
"""

import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone

from mididivisi.core.parser import load_score
from mididivisi.core.session import Session, Instrument, Group
from mididivisi.core.settings import settings as live_settings
from mididivisi.core.profiles import library

FORMAT_VERSION = 1


def _settings_snapshot(settings_obj):
    return {
        "keyword_mapping": settings_obj.keyword_mapping,
        "dynamics_mapping": settings_obj.dynamics_mapping,
        "accent_velocity_multiplier": settings_obj.accent_velocity_multiplier,
    }


def _serialize_session(session):
    instruments_data = []

    for instrument in session.instruments:
        groups_data = []
        for group in instrument.groups:
            groups_data.append(
                {
                    "name": group.name,
                    "included": group.included,
                    "track_keys": [list(t.natural_key) for t in group.tracks],
                    # Which InventoryItem (from the instrument's
                    # assigned Profile, if any) this group corresponds
                    # to - by id, not embedded data, since Profiles are
                    # a live, editable resource re-resolved against
                    # its CURRENT state on load (same philosophy as
                    # natural-key track resolution), not frozen at
                    # save time.
                    "profile_item_id": group.profile_item.id if group.profile_item else None,
                }
            )

        instruments_data.append(
            {
                "name": instrument.name,
                "included": instrument.included,
                "identity_keys": [list(ident.natural_key) for ident in instrument.identities],
                "groups": groups_data,
                "profile_id": instrument.profile.id if instrument.profile else None,
                "keyswitch_enabled": instrument.keyswitch_enabled,
            }
        )

    return {"instruments": instruments_data}


def save_session(session, original_score_path, output_path):
    """Save the current session, a copy of the original score, and a
    snapshot of current Settings, all bundled into one .mididivisi
    zip file at output_path.
    """
    manifest = {
        "format_version": FORMAT_VERSION,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "original_filename": os.path.basename(original_score_path),
    }

    session_data = _serialize_session(session)
    settings_data = _settings_snapshot(live_settings)

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        zf.writestr("session.json", json.dumps(session_data, indent=2))
        zf.writestr("settings_snapshot.json", json.dumps(settings_data, indent=2))
        zf.write(original_score_path, arcname="score.musicxml")


class SessionLoadResult:
    """Intermediate result from start_loading_session, before the
    caller has decided which Settings to use (only relevant if they
    differ from the live ones). Pass this to finish_loading_session
    along with that decision to get the actual Session object.
    """

    def __init__(self, temp_score_path, temp_dir, session_data, saved_settings, settings_differ):
        self.temp_score_path = temp_score_path
        self.temp_dir = temp_dir  # cleaned up by the caller once loading is done
        self.session_data = session_data
        self.saved_settings = saved_settings
        self.settings_differ = settings_differ


def start_loading_session(input_path):
    """Open a .mididivisi file, extract the embedded score to a temp
    location, and compare the embedded settings snapshot against the
    live Settings - WITHOUT yet parsing the score or applying any
    settings choice. Returns a SessionLoadResult for the caller to
    finish with finish_loading_session() once any needed settings
    choice is known.
    """
    with zipfile.ZipFile(input_path, "r") as zf:
        # manifest is read but not yet used beyond existing - no
        # format-version branching needed until there's more than one
        # version to handle.
        json.loads(zf.read("manifest.json"))
        session_data = json.loads(zf.read("session.json"))
        saved_settings = json.loads(zf.read("settings_snapshot.json"))

        temp_dir = tempfile.mkdtemp(prefix="mididivisi_")
        temp_score_path = os.path.join(temp_dir, "score.musicxml")
        with zf.open("score.musicxml") as src, open(temp_score_path, "wb") as dst:
            shutil.copyfileobj(src, dst)

    current_settings = _settings_snapshot(live_settings)
    differ = current_settings != saved_settings

    return SessionLoadResult(temp_score_path, temp_dir, session_data, saved_settings, differ)


def finish_loading_session(load_result, use_saved_settings):
    """Complete a session load, given the user's choice (if prompted)
    of whether to use the saved settings snapshot or keep the current
    live settings. If saved settings are chosen, they're applied to
    the live Settings instance AND persisted to disk - same as any
    other settings change in this app, not a temporary override.

    Re-parses the embedded score (using whichever settings are now
    active) and reconstructs the exact saved Instrument/Group
    structure via direct construction, using natural-key lookups
    against the freshly parsed tracks/identities.

    Returns (session, warnings) - warnings is a list of human-readable
    strings for any saved natural key that no longer exists in the
    freshly parsed score (e.g. the underlying score changed, or a
    Settings change altered detection) - those entries are simply
    skipped rather than crashing the load.

    Does NOT clean up the temp directory - see this module's
    docstring for why (the caller keeps using temp_score_path as the
    session's current score afterward).
    """
    if use_saved_settings:
        live_settings.keyword_mapping = {
            k: list(v) for k, v in load_result.saved_settings["keyword_mapping"].items()
        }
        live_settings.dynamics_mapping = dict(load_result.saved_settings["dynamics_mapping"])
        live_settings.accent_velocity_multiplier = load_result.saved_settings[
            "accent_velocity_multiplier"
        ]
        live_settings.save()

    score = load_score(load_result.temp_score_path)
    fresh_session = Session.from_score(score)

    tracks_by_key = {t.natural_key: t for t in fresh_session.tracks}
    identities_by_key = {ident.natural_key: ident for ident in fresh_session.instrument_identities}

    warnings = []
    new_session = Session()
    new_session.tracks = fresh_session.tracks
    new_session.instrument_identities = fresh_session.instrument_identities
    new_session.tempo_events = fresh_session.tempo_events

    for instr_data in load_result.session_data["instruments"]:
        identities = []
        for key in instr_data["identity_keys"]:
            key_t = tuple(key)
            ident = identities_by_key.get(key_t)
            if ident is None:
                warnings.append(f"Instrument {key_t} no longer found in the score - skipped")
                continue
            identities.append(ident)

        if not identities:
            continue

        # Resolve the instrument's Profile assignment FIRST (by id,
        # against the live ProfileLibrary - a Profile is an editable,
        # reusable resource, so a reload should reflect its CURRENT
        # state, not a frozen snapshot) - needed before groups are
        # built below, since each group's profile_item is looked up
        # within THIS profile's inventory.
        resolved_profile = None
        profile_id = instr_data.get("profile_id")
        if profile_id is not None:
            _, resolved_profile = library.find_profile(profile_id)
            if resolved_profile is None:
                warnings.append(
                    f"Profile assigned to '{instr_data['name']}' no longer exists "
                    f"- profile assignment cleared"
                )

        groups = []
        for group_data in instr_data["groups"]:
            tracks = []
            for key in group_data["track_keys"]:
                key_t = tuple(key)
                track = tracks_by_key.get(key_t)
                if track is None:
                    warnings.append(f"Track {key_t} no longer found in the score - skipped")
                    continue
                tracks.append(track)

            if not tracks:
                continue

            group = Group(group_data["name"], tracks)
            group.included = group_data["included"]

            profile_item_id = group_data.get("profile_item_id")
            if profile_item_id is not None and resolved_profile is not None:
                matching_item = next(
                    (item for item in resolved_profile.inventory if item.id == profile_item_id),
                    None,
                )
                if matching_item is not None:
                    group.profile_item = matching_item
                else:
                    warnings.append(
                        f"Articulation bucket for group '{group_data['name']}' no longer "
                        f"exists in its profile"
                    )

            groups.append(group)

        if not groups:
            continue

        instrument = Instrument(instr_data["name"], identities, groups)
        instrument.included = instr_data["included"]
        instrument.profile = resolved_profile
        if resolved_profile is not None:
            instrument.keyswitch_enabled = instr_data.get("keyswitch_enabled", False)
        new_session.instruments.append(instrument)

    return new_session, warnings
