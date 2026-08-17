"""
MIDI export logic.

Takes the note/chord groups produced by core.parser and writes them
out as MIDI. Built on music21's own Stream -> MIDI writer rather than
hand-rolling MIDI bytes, since we already have music21 Note/Chord
objects with correct offset (timing) and duration data from parsing.
"""

import copy
import os
import re

from music21 import instrument as m21_instrument
from music21 import note, stream, tempo

from mididivisi.core.parser import get_part_articulation_groups

# Keyswitch note-on duration/velocity when flattening a keyswitch-
# enabled instrument into one track. The exact values don't matter
# much functionally - just needs to be short (so it doesn't audibly
# overlap the real notes it precedes) and non-zero velocity (a MIDI
# note-on with velocity 0 is equivalent to a note-off per spec, which
# would make the keyswitch invisible to some strict readers).
KEYSWITCH_NOTE_DURATION = 0.1
KEYSWITCH_NOTE_VELOCITY = 100


def export_group_to_midi(notes, output_path):
    """Write a single articulation group (a list of Note/Chord objects)
    out as a one-track MIDI file, preserving each note's original
    offset (start time) and duration.

    notes objects are deep-copied before inserting into a fresh Stream,
    so this never mutates the original parsed score data.
    """
    s = stream.Stream()

    for n in notes:
        n_copy = copy.deepcopy(n)
        s.insert(n.offset, n_copy)

    s.write("midi", fp=output_path)


def _build_midi_track(track_name, notes):
    """Build one MIDI Part/track with the given name, containing the
    given notes. The single low-level primitive both the legacy
    score-based export functions and the newer Session-based ones
    build on.
    """
    track = stream.Part()

    # Setting .partName on the Part alone does NOT produce a MIDI
    # track_name meta event - music21's MIDI writer reads the name
    # from an Instrument object inserted into the stream instead.
    # Verified directly against exported bytes.
    track_instrument = m21_instrument.Instrument()
    track_instrument.partName = track_name
    track.insert(0, track_instrument)

    for n in notes:
        n_copy = copy.deepcopy(n)
        track.insert(n.offset, n_copy)

    return track


def _build_instrument_tracks(part, instrument_name):
    """Build one MIDI Part/track per articulation group found in a
    single music21 Part, named "<instrument> - <label>" (or
    "<instrument> (<routing>) - <label>" for a divisi/solo routing).
    Shared by both legacy (score-based) export modes below - a
    whole-score export just collects every part's tracks into one
    file, while per-instrument export writes each part's tracks into
    their own file.

    NOTE: this legacy path is NOT reachable from the actual app (which
    always goes through the Session-based export functions further
    down) - confirmed via a direct search before touching it. Fixed
    for consistency with get_part_articulation_groups's routing/label
    key split anyway, rather than leaving known-broken dead code
    around.
    """
    groups = get_part_articulation_groups(part)
    tracks = []
    for (routing, label), notes in groups.items():
        name = f"{instrument_name} ({routing}) - {label}" if routing else f"{instrument_name} - {label}"
        tracks.append(_build_midi_track(name, notes))
    return tracks


def export_score_to_midi(score, output_path):
    """Walk every part in a parsed score, group notes by articulation
    (same grouping used for the console breakdown), and write the
    whole thing out as ONE multi-track MIDI file. Each
    (instrument, articulation) group becomes its own MIDI track,
    named "<instrument> - <label>" so it's recognizable once it lands
    in a DAW.

    Parts with no notes (e.g. tacet parts, or gaps like unpitched
    percussion that we don't parse yet) simply produce no tracks -
    nothing to export for them yet.
    """
    out_score = stream.Score()

    for part in score.parts:
        instrument_name = part.partName or "(unnamed part)"
        for track in _build_instrument_tracks(part, instrument_name):
            out_score.insert(0, track)

    out_score.write("midi", fp=output_path)


def _sanitize_filename(name):
    """Turn an instrument name into a safe filename: strip characters
    that are invalid (or awkward) on Windows/Mac filesystems.
    """
    # Replace anything that isn't alphanumeric, space, dash, or
    # underscore with an underscore, then collapse repeated
    # whitespace.
    safe = re.sub(r"[^\w\s-]", "_", name)
    safe = re.sub(r"\s+", " ", safe).strip()
    return safe or "unnamed_instrument"


def _insert_tempo_events(out_score, tempo_events):
    """Insert (offset, bpm) tempo events directly onto the output
    Score object (not into any Part) - verified this makes music21
    write them into their own separate conductor track, leaving every
    actual data track untouched. Without this, exported MIDI had NO
    tempo information at all, meaning any DAW reading it back would
    silently assume its own default tempo (commonly 120 BPM)
    regardless of the real piece's actual tempo - a real, guaranteed-
    to-matter correctness gap, not an edge case (every real test file
    used in development had an actual tempo other than 120).
    """
    for offset, bpm in tempo_events:
        out_score.insert(offset, tempo.MetronomeMark(number=bpm))


def export_score_to_midi_per_instrument(score, output_dir):
    """Same grouping as export_score_to_midi, but writes ONE MIDI file
    per instrument/part into output_dir, instead of combining
    everything into a single file. Each file still contains multiple
    tracks internally - one per articulation group for that
    instrument.

    Parts with no notes are skipped entirely (no empty file written).
    Instrument names that repeat (e.g. grand-staff duplicates like
    Harp appearing as two separate parts) get a numeric suffix so
    files don't silently overwrite each other.

    Returns the list of file paths actually written.
    """
    written_paths = []
    used_filenames = {}

    for part in score.parts:
        instrument_name = part.partName or "(unnamed part)"
        tracks = _build_instrument_tracks(part, instrument_name)

        if not tracks:
            continue  # nothing to export for this part

        base_filename = _sanitize_filename(instrument_name)

        # Disambiguate repeated instrument names (e.g. two "Harp"
        # parts from a grand staff) so we don't overwrite files.
        count = used_filenames.get(base_filename, 0)
        used_filenames[base_filename] = count + 1
        filename = base_filename if count == 0 else f"{base_filename} ({count + 1})"

        output_path = os.path.join(output_dir, f"{filename}.mid")

        out_score = stream.Score()
        for track in tracks:
            out_score.insert(0, track)
        out_score.write("midi", fp=output_path)

        written_paths.append(output_path)

    return written_paths


def _flatten_instrument_with_keyswitches(instr):
    """Combine an instrument's INCLUDED, MATCHED groups (those with a
    real profile_item) into ONE time-ordered list of notes, with a
    keyswitch note-on inserted whenever the active articulation bucket
    changes from one note to the next.

    Groups with no profile_item (an articulation the assigned profile
    doesn't define a keyword for) are DELIBERATELY EXCLUDED here, not
    included-but-unswitched - see _build_instrument_export_tracks,
    which exports them as their own separate track(s) instead. Folding
    them into this flattened track with no keyswitch cue would be a
    real correctness problem, not just a cosmetic one: the sampler
    would keep playing on whatever patch the PREVIOUS keyswitch last
    selected, which is very likely wrong for the unmatched passage.

    KNOWN LIMITATION, accepted rather than solved (see BACKLOG.md):
    if two different MATCHED groups have notes at the exact same
    offset (a genuinely simultaneous multi-articulation moment), the
    inserted keyswitch note-on could collide with real notes from the
    other group at that same instant. Not addressed here.
    """
    timeline = []
    for group in instr.groups:
        if not group.included:
            continue
        if group.profile_item is None:
            continue  # exported as its own separate track instead - see above
        for n in group.get_combined_notes():
            timeline.append((n.offset, group, n))

    timeline.sort(key=lambda entry: entry[0])

    result_notes = []
    current_group_id = None

    for offset, group, n in timeline:
        if group.id != current_group_id:
            current_group_id = group.id
            item = group.profile_item
            if item.keyswitch_note is not None:
                ks_note = note.Note(midi=item.keyswitch_note, quarterLength=KEYSWITCH_NOTE_DURATION)
                ks_note.offset = offset
                ks_note.volume.velocity = KEYSWITCH_NOTE_VELOCITY
                ks_note.volume.velocityIsRelative = False
                result_notes.append(ks_note)
        result_notes.append(n)

    return result_notes


def _build_instrument_export_tracks(instr):
    """Decide, for one Instrument, whether it exports as one flattened
    keyswitch track or as separate tracks per group (today's default
    behavior) - shared by both export_session_to_midi and
    export_session_to_midi_per_instrument so this decision only lives
    in one place. Returns a list of (track_name, notes) tuples, notes
    already filtered to non-empty.

    When keyswitching is active, MATCHED groups (profile_item is not
    None) combine into one flattened track - but UNMATCHED groups
    (an articulation the profile has no keyword for) still export as
    their own separate track(s), same as if keyswitching were off
    just for them. See _flatten_instrument_with_keyswitches for why
    folding them in silently would be actively wrong, not just
    unhelpful.
    """
    keyswitching_active = (
        instr.keyswitch_enabled
        and instr.profile is not None
        and instr.profile.keyswitch_enabled
    )

    if not keyswitching_active:
        tracks = [(g.name, g.get_combined_notes()) for g in instr.groups if g.included]
        return [(name, notes) for name, notes in tracks if notes]

    result = []

    flattened_notes = _flatten_instrument_with_keyswitches(instr)
    if flattened_notes:
        result.append((instr.name, flattened_notes))

    for group in instr.groups:
        if not group.included or group.profile_item is not None:
            continue
        notes = group.get_combined_notes()
        if notes:
            result.append((group.name, notes))

    return result


def export_session_to_midi(session, output_path):
    """Export a Session's currently-included instruments/groups as ONE
    multi-track MIDI file. Each Group normally becomes its own track,
    using the Group's CURRENT name (auto-generated label, a user
    rename, or a merged-group name) - UNLESS an instrument has
    keyswitching enabled (Instrument.keyswitch_enabled, plus its
    assigned Profile also having keyswitch_enabled), in which case
    that whole instrument becomes ONE flattened track with keyswitch
    note-ons inserted (see _build_instrument_export_tracks).

    Groups/tracks with zero notes are skipped rather than writing an
    empty track.
    """
    out_score = stream.Score()
    _insert_tempo_events(out_score, session.tempo_events)

    for instr in session.instruments:
        if not instr.included:
            continue
        for track_name, notes in _build_instrument_export_tracks(instr):
            out_score.insert(0, _build_midi_track(track_name, notes))

    out_score.write("midi", fp=output_path)


def export_session_to_midi_per_instrument(session, output_dir):
    """Same idea as export_session_to_midi, but writes one MIDI file
    per Instrument into output_dir - one file per row shown in the
    UI's instrument-header level, reflecting current names, any
    instrument-level merges, and keyswitch flattening where enabled
    (see _build_instrument_export_tracks).

    Instrument names that repeat (e.g. two un-merged "Harp" instruments
    from a grand staff) get a numeric suffix so files don't silently
    overwrite each other.

    An instrument with included=False is skipped entirely, even if
    some of its groups individually have included=True (same gating
    rule as Session.get_export_groups).

    Returns the list of file paths actually written.
    """
    written_paths = []
    used_filenames = {}

    for instr in session.instruments:
        if not instr.included:
            continue

        tracks_with_notes = _build_instrument_export_tracks(instr)

        if not tracks_with_notes:
            continue  # nothing included/with notes for this instrument

        base_filename = _sanitize_filename(instr.name)

        count = used_filenames.get(base_filename, 0)
        used_filenames[base_filename] = count + 1
        filename = base_filename if count == 0 else f"{base_filename} ({count + 1})"

        output_path = os.path.join(output_dir, f"{filename}.mid")

        out_score = stream.Score()
        _insert_tempo_events(out_score, session.tempo_events)
        for track_name, notes in tracks_with_notes:
            out_score.insert(0, _build_midi_track(track_name, notes))
        out_score.write("midi", fp=output_path)

        written_paths.append(output_path)

    return written_paths
