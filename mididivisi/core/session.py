"""
Session data model.

Three tiers of state that persist independently of the raw music21
score data, which is what actually enables non-destructive
rename/merge/split at both the articulation level AND the instrument
level:

- Track: one base articulation group exactly as the parser originally
  detected it (e.g. "Violin I - Staccato"). Created once when a score
  is loaded and never destroyed - only its `name` is ever changed, and
  that persists for the life of the session. Permanently linked to the
  one InstrumentIdentity it came from.

- InstrumentIdentity: one per ORIGINAL part in the score (e.g. the two
  separate "Harp" parts from a grand staff each get their own
  identity, even though they share a display name). Permanent, never
  destroyed - only its `name` changes, and that persists the same way
  a Track's name does.

- Group: what the UI shows as one articulation-level row / one
  exportable unit. References one or more Tracks. Merging combines
  multiple Groups' track lists into one; splitting dissolves a merged
  Group back into one Group per original Track, each resurfacing
  whatever name it privately had all along.

- Instrument: what the UI shows as one instrument header. References
  one or more InstrumentIdentity objects, and owns the current list of
  Groups displayed under it. Merging two Instruments auto-merges any
  matching (same-label, not-already-merged) Groups between them, and
  carries over anything that doesn't match unchanged. Splitting
  reverses this, including un-merging any Groups that only existed
  because the instrument merge created them.

Note data itself is never touched by merge/split - only export
(Session.get_export_groups) actually combines note lists together,
and only at that final step. Everything before that is just deciding
which Tracks are currently grouped under which Group, and which
Groups are currently owned by which Instrument.
"""

import uuid

from mididivisi.core.parser import get_part_articulation_groups


class Track:
    """One base articulation group, as originally detected by the
    parser. Created once at load time and never destroyed - identity
    is permanent for the life of the session. `name` is the only
    mutable field, and it persists across merge/split. Permanently
    linked to the one InstrumentIdentity it came from (this link never
    changes, regardless of which Instrument currently contains it).
    """

    def __init__(self, instrument_identity, label, notes):
        self.id = str(uuid.uuid4())
        self.instrument_identity = instrument_identity  # permanent link, never changes
        self.label = label  # original articulation label, provenance, never changes
        self.notes = notes  # list of music21 Note/Chord objects, never mutated here
        self.name = f"{instrument_identity.name} - {label}"  # mutable, user-editable

    @property
    def natural_key(self):
        """A stable identity that survives re-parsing the SAME
        MusicXML file, unlike .id (a fresh random UUID every parse).
        Used for session save/load - re-parsing the same file in the
        same order deterministically reproduces the same natural
        keys, even though .id differs every time. See
        InstrumentIdentity.natural_key for the instrument-level half
        of this key.
        """
        return self.instrument_identity.natural_key + (self.label,)

    def __repr__(self):
        return f"Track(name={self.name!r}, notes={len(self.notes)})"


class InstrumentIdentity:
    """Permanent identity for one ORIGINAL part in the score. Exactly
    one is created per part when the score is first loaded - so two
    parts that happen to share a display name (e.g. a grand-staff
    instrument like Harp, split into two music21 Parts) get two
    distinct identities, never conflated. `name` is mutable and
    persists across merge/split, same guarantee as Track.name.
    """

    def __init__(self, original_name, occurrence_index=0):
        self.id = str(uuid.uuid4())
        self.original_name = original_name  # immutable provenance
        self.name = original_name  # mutable, user-editable, persists
        # Which occurrence this is among parts sharing the same
        # original_name (e.g. the two "Harp" parts from a grand staff
        # get occurrence_index 0 and 1) - needed because original_name
        # ALONE isn't unique, but (original_name, occurrence_index)
        # is, and is stable across re-parsing the same file in the
        # same order. See natural_key.
        self.occurrence_index = occurrence_index

    @property
    def natural_key(self):
        """A stable identity that survives re-parsing the SAME
        MusicXML file, unlike .id (a fresh random UUID every parse).
        Used for session save/load.
        """
        return (self.original_name, self.occurrence_index)

    def __repr__(self):
        return f"InstrumentIdentity(name={self.name!r})"


class Group:
    """One row in the UI / one exportable unit. References one or more
    Tracks. `included` always resets to True whenever a Group is newly
    formed - whether that's the initial single-Track state, the result
    of a merge, or the result of a split - it is NOT preserved across
    those operations, per design decision (simpler than trying to
    remember/restore prior checked-state).
    """

    def __init__(self, name, tracks):
        self.id = str(uuid.uuid4())
        self.name = name
        self.tracks = list(tracks)  # one or more Track objects
        self.included = True
        # Set by Session.apply_profile when this group was formed from
        # a profile's inventory bucket - the InventoryItem (from
        # core/profiles.py) it corresponds to, or None for groups not
        # tied to any profile bucket (manual merges, unmatched
        # tracks). Lets the UI show that item's keyswitch note without
        # re-deriving the label-matching logic apply_profile already
        # did.
        self.profile_item = None

    @property
    def is_merged(self):
        return len(self.tracks) > 1

    def rename(self, new_name):
        """Rename this group. If it's currently a single-track
        (unmerged) group, the rename ALSO propagates down to that
        Track's own persisted name - for an unmerged group, the group
        and its one track represent the same real-world thing, so a
        rename should update the identity that needs to survive a
        future merge, not just this transient Group wrapper.

        If the group is already merged, the rename stays local to the
        Group only - there's no single track to attribute it to, and
        each member track should resurface with ITS OWN prior name
        when eventually split, not this merged name.
        """
        self.name = new_name
        if not self.is_merged:
            self.tracks[0].name = new_name

    def get_combined_notes(self):
        """Combine every member Track's notes into one list. Only
        meant to be called at export time - never mutates the
        underlying Tracks, so this is always safe to call repeatedly
        (e.g. if the user exports, adjusts a track, exports again).
        """
        combined = []
        for track in self.tracks:
            combined.extend(track.notes)
        return combined

    def __repr__(self):
        return (
            f"Group(name={self.name!r}, tracks={len(self.tracks)}, "
            f"included={self.included})"
        )


class Instrument:
    """One instrument header in the UI. References one or more
    InstrumentIdentity objects (more than one only after a merge), and
    owns the current list of Groups displayed under it. A freshly-
    loaded score starts as one single-identity Instrument per original
    part.
    """

    def __init__(self, name, identities, groups):
        self.id = str(uuid.uuid4())
        self.name = name
        self.identities = list(identities)
        self.groups = list(groups)
        self.included = True
        # Profile assignment (see core/profiles.py). None until the
        # user explicitly assigns one via the Select Profile picker -
        # never inferred/auto-assigned. keyswitch_enabled only means
        # anything if self.profile is set AND has at least one
        # keyswitch defined (Profile.has_keyswitches) - the UI's KS
        # toggle is meant to be disabled otherwise.
        self.profile = None
        self.keyswitch_enabled = False

    @property
    def is_merged(self):
        return len(self.identities) > 1

    def rename(self, new_name):
        """Rename this instrument. Same propagation rule as
        Group.rename: if this is currently a single-identity
        (unmerged) instrument, the rename ALSO updates that identity's
        persisted name, so it resurfaces correctly on a future merge.
        If already merged, the rename stays local to the Instrument.
        """
        self.name = new_name
        if not self.is_merged:
            self.identities[0].name = new_name

    def __repr__(self):
        return (
            f"Instrument(name={self.name!r}, identities={len(self.identities)}, "
            f"groups={len(self.groups)})"
        )


class Session:
    """Holds every Track and InstrumentIdentity ever created for this
    session (both permanent) and the current list of Instruments (the
    editable view the UI works with) for one loaded score. `groups` is
    a derived/flattened view across every Instrument's current groups
    - not separately maintained state, so there's only one place
    (Instrument.groups) that actually owns a Group at a time.
    """

    def __init__(self):
        self.tracks = []
        self.instrument_identities = []
        self.instruments = []

    @property
    def groups(self):
        result = []
        for instrument in self.instruments:
            result.extend(instrument.groups)
        return result

    @classmethod
    def from_score(cls, score):
        """Build a fresh Session from a just-loaded music21 score: one
        InstrumentIdentity and one single-identity Instrument per
        part, one Track (and one single-member Group) per
        (instrument, articulation) combination the parser detects.
        Nothing is merged automatically at either level - matches the
        explicit "no auto-merge on load" decision.
        """
        session = cls()
        occurrence_counts = {}  # original_name -> how many seen so far, for natural_key

        for part in score.parts:
            part_name = part.partName or "(unnamed part)"
            occurrence_index = occurrence_counts.get(part_name, 0)
            occurrence_counts[part_name] = occurrence_index + 1

            identity = InstrumentIdentity(part_name, occurrence_index)
            session.instrument_identities.append(identity)

            articulation_groups = get_part_articulation_groups(part)
            groups_for_instrument = []

            for label, notes in articulation_groups.items():
                track = Track(identity, label, notes)
                session.tracks.append(track)
                group = Group(track.name, [track])
                groups_for_instrument.append(group)

            instrument = Instrument(identity.name, [identity], groups_for_instrument)
            session.instruments.append(instrument)

        return session

    def _find_owning_instrument(self, group):
        for instrument in self.instruments:
            if group in instrument.groups:
                return instrument
        return None

    def merge_groups(self, group_ids):
        """Merge two or more groups into one. The new group's name
        comes from whichever group is FIRST in group_ids (the
        "first-selected" group), using that group's current name
        as-is. The merged group is always included=True regardless of
        the members' prior included state.

        All groups being merged must currently belong to the SAME
        Instrument - this mirrors the UI rule (merge is only offered
        for same-instrument selections), enforced here too as a
        safety check rather than trusting the caller blindly.

        Track objects themselves are completely untouched - this only
        changes which Group currently references them.
        """
        if len(group_ids) < 2:
            raise ValueError("Need at least 2 group ids to merge")

        groups_by_id = {g.id: g for g in self.groups}

        missing = [gid for gid in group_ids if gid not in groups_by_id]
        if missing:
            raise ValueError(f"No group(s) with id(s): {missing}")

        # Preserve the caller's ordering (not internal order) so
        # "first in group_ids" unambiguously determines the resulting
        # name.
        ordered_groups = [groups_by_id[gid] for gid in group_ids]

        owning_instruments = {self._find_owning_instrument(g).id for g in ordered_groups}
        if len(owning_instruments) > 1:
            raise ValueError(
                "Cannot merge groups belonging to different instruments"
            )

        owning_instrument = self._find_owning_instrument(ordered_groups[0])

        new_name = ordered_groups[0].name
        all_tracks = []
        for g in ordered_groups:
            all_tracks.extend(g.tracks)

        new_group = Group(new_name, all_tracks)

        group_id_set = set(group_ids)
        owning_instrument.groups = [
            g for g in owning_instrument.groups if g.id not in group_id_set
        ]
        owning_instrument.groups.append(new_group)

        return new_group

    def split_group(self, group_id):
        """Dissolve a merged group back into one single-member group
        per original Track. Each resulting group shows that Track's
        own (persisted) name, and is included=True.

        Splitting a group that was never merged (only 1 track) is a
        no-op that just returns the group unchanged in a list, since
        there's nothing to split.
        """
        group = next((g for g in self.groups if g.id == group_id), None)
        if group is None:
            raise ValueError(f"No group with id {group_id}")

        if not group.is_merged:
            return [group]

        owning_instrument = self._find_owning_instrument(group)
        owning_instrument.groups.remove(group)

        new_groups = []
        for track in group.tracks:
            new_group = Group(track.name, [track])
            owning_instrument.groups.append(new_group)
            new_groups.append(new_group)

        return new_groups

    def merge_instruments(self, instrument_ids):
        """Merge two or more instruments into one. The new
        instrument's name comes from whichever instrument is FIRST in
        instrument_ids. Groups are auto-matched across the merging
        instruments by articulation LABEL (not display name, which is
        mutable) and combined via the same merge logic as
        merge_groups - but ONLY when a group is a plain, unmerged,
        single-track group. A group that's already been merged with
        something else has no unambiguous single label to match
        against, so it's left untouched and simply carried over
        alongside everything else - this is a deliberate, documented
        simplification, not an oversight.

        Non-matching groups (an articulation present on one instrument
        but not the other) are carried over unchanged.
        """
        if len(instrument_ids) < 2:
            raise ValueError("Need at least 2 instrument ids to merge")

        instruments_by_id = {i.id: i for i in self.instruments}

        missing = [iid for iid in instrument_ids if iid not in instruments_by_id]
        if missing:
            raise ValueError(f"No instrument(s) with id(s): {missing}")

        ordered_instruments = [instruments_by_id[iid] for iid in instrument_ids]

        new_name = ordered_instruments[0].name
        all_identities = []
        for instr in ordered_instruments:
            all_identities.extend(instr.identities)

        # Bucket every MATCHABLE (single-track, unmerged) group by its
        # track's articulation label. Already-merged groups go
        # straight into carry_over_groups untouched.
        groups_by_label = {}
        carry_over_groups = []

        for instr in ordered_instruments:
            for group in instr.groups:
                if group.is_merged:
                    carry_over_groups.append(group)
                else:
                    label = group.tracks[0].label
                    groups_by_label.setdefault(label, []).append(group)

        new_groups = list(carry_over_groups)

        for label, matching_groups in groups_by_label.items():
            if len(matching_groups) >= 2:
                all_tracks = []
                for g in matching_groups:
                    all_tracks.extend(g.tracks)
                # Name follows the same "first-selected wins" rule,
                # using whichever matching group came from the
                # first-selected instrument.
                new_groups.append(Group(matching_groups[0].name, all_tracks))
            else:
                new_groups.append(matching_groups[0])

        new_instrument = Instrument(new_name, all_identities, new_groups)

        instrument_id_set = set(instrument_ids)
        self.instruments = [
            i for i in self.instruments if i.id not in instrument_id_set
        ]
        self.instruments.append(new_instrument)

        return new_instrument

    def split_instrument(self, instrument_id):
        """Dissolve a merged instrument back into one Instrument per
        original InstrumentIdentity, each showing that identity's own
        (persisted) name.

        Any currently-owned Group whose tracks span MORE THAN ONE of
        the identities being split (i.e. it only exists because the
        instrument merge auto-matched it) is itself split back apart
        first, so every track ends up routed to the correct identity's
        new Instrument. Groups that only ever contained tracks from a
        single identity move over intact.

        Splitting an instrument that was never merged (only 1
        identity) is a no-op that just returns it unchanged in a list.
        """
        instrument = next((i for i in self.instruments if i.id == instrument_id), None)
        if instrument is None:
            raise ValueError(f"No instrument with id {instrument_id}")

        if not instrument.is_merged:
            return [instrument]

        self.instruments.remove(instrument)

        resolved_groups = []
        for group in instrument.groups:
            identities_in_group = {t.instrument_identity.id for t in group.tracks}
            if len(identities_in_group) > 1:
                # Cross-identity merged group - split it back into one
                # group per track so each can be routed correctly.
                for track in group.tracks:
                    resolved_groups.append(Group(track.name, [track]))
            else:
                resolved_groups.append(group)

        new_instruments = []
        for identity in instrument.identities:
            owned_groups = [
                g for g in resolved_groups
                if g.tracks[0].instrument_identity.id == identity.id
            ]
            new_instrument = Instrument(identity.name, [identity], owned_groups)
            self.instruments.append(new_instrument)
            new_instruments.append(new_instrument)

        return new_instruments

    def apply_profile(self, instrument_id, profile):
        """Apply a Profile (see core/profiles.py) to one Instrument:
        rebuild its groups from scratch according to the profile's
        articulation inventory, and record the assignment.

        Only ever touches instrument.groups - NEVER instrument.identities
        or self.instruments. This is deliberate: it's what guarantees
        applying a profile can never un-merge an already-merged
        instrument (e.g. a merged pair of grand-staff Harps), since
        instrument-merge structure and group-level organization are
        two independent axes in this data model, and profile
        application only ever operates on the second one.

        Every currently-owned Track (regardless of which Group it's
        presently in, or how it got there) is gathered up first, then
        re-sorted: a Track matching one of the profile's inventory
        items (via its permanent, unrenameable .label) joins that
        item's group, named after the LIBRARY'S bucket name (e.g.
        "Violin I - Short") - NOT the "first-selected wins" naming
        rule manual merges use, since the whole point of a profile is
        imposing the library's own naming. Any track matching no
        inventory item becomes its own single-track group again,
        keeping whatever name it already had.

        This is a genuine override, per design: reapplying a profile
        (or applying a different one) always rebuilds groups from
        scratch, discarding whatever manual group-level merging/
        renaming existed before. instrument.keyswitch_enabled is also
        reset to False - a fresh profile assignment doesn't inherit
        the previous profile's keyswitch toggle state.
        """
        instrument = next((i for i in self.instruments if i.id == instrument_id), None)
        if instrument is None:
            raise ValueError(f"No instrument with id {instrument_id}")

        all_tracks = []
        for group in instrument.groups:
            all_tracks.extend(group.tracks)

        # label -> matching InventoryItem, built once for O(1) lookup
        # instead of re-scanning every item's matched_labels per track.
        label_to_item = {}
        for item in profile.inventory:
            for label in item.matched_labels:
                label_to_item[label] = item

        tracks_by_item_id = {}
        unmatched_tracks = []

        for track in all_tracks:
            item = label_to_item.get(track.label)
            if item is None:
                unmatched_tracks.append(track)
            else:
                tracks_by_item_id.setdefault(item.id, []).append(track)

        new_groups = []
        for item in profile.inventory:
            matched = tracks_by_item_id.get(item.id)
            if matched:
                new_group = Group(f"{instrument.name} - {item.name}", matched)
                new_group.profile_item = item
                new_groups.append(new_group)

        for track in unmatched_tracks:
            new_groups.append(Group(track.name, [track]))

        instrument.groups = new_groups
        instrument.profile = profile
        instrument.keyswitch_enabled = False

    def merge_accent_variants(self):
        """Auto-merge any single-track group whose raw articulation
        label includes Accent into the corresponding non-accented
        group WITHIN THE SAME INSTRUMENT, if one currently exists
        (e.g. "Staccato+Accent" merges into "Staccato"; a lone
        "Accent" merges into "Sustain"). Accented notes stay separated
        by default - this is an opt-in action, not automatic on load,
        for people who don't have (or don't want) a dedicated
        accented-technique patch.

        StrongAccent is deliberately EXCLUDED from this, same
        reasoning as the velocity amplifier in parser.py's
        apply_dynamics_to_part: MusicXML has no separate "marcato"
        element, so the marcato "^" symbol IS StrongAccent, and
        marcato is meant to stay fully separate rather than folding
        into its base technique automatically.

        The "corresponding technique" is looked for among ANY current
        group's member tracks (merged or not) - not just single-track
        groups - so if multiple Accent-labeled groups exist for the
        same base for some reason, the first merge creates the base
        bucket and later ones correctly find and join it, rather than
        only matching on the first pass. Only single-track groups are
        ever the thing being ABSORBED, since an already-merged group
        has no single unambiguous label to strip Accent from.

        The base technique's current name always wins (it's passed
        first to merge_groups), same "first-selected" naming rule
        used everywhere else.

        Velocity amplification for accented notes is independent of
        this - it's applied to the note data itself at parse time
        (see parser.py's apply_dynamics_to_part), so it survives
        regardless of whether this merge ever runs.

        Returns the number of merge operations performed.
        """
        merges_done = 0

        for instrument in self.instruments:
            while True:
                found_pair = None

                for group in instrument.groups:
                    if group.is_merged:
                        continue  # only single-track groups can be absorbed

                    label = group.tracks[0].label
                    parts = label.split("+")
                    if "Accent" not in parts:
                        continue

                    remaining = [p for p in parts if p != "Accent"]
                    base_label = "+".join(remaining) if remaining else "Sustain"

                    base_group = next(
                        (
                            g for g in instrument.groups
                            if g.id != group.id
                            and any(t.label == base_label for t in g.tracks)
                        ),
                        None,
                    )
                    if base_group is not None:
                        found_pair = (base_group, group)
                        break

                if found_pair is None:
                    break

                base_group, accent_group = found_pair
                self.merge_groups([base_group.id, accent_group.id])
                merges_done += 1

        return merges_done

    def get_export_groups(self):
        """Return the currently-included groups, ready for export.
        A group is only included in the result if BOTH its own
        `included` flag is True AND its owning Instrument's
        `included` flag is True - unchecking an instrument acts as a
        gate over its children, even if an individual group underneath
        it still has included=True from before the instrument was
        unchecked (that value is deliberately preserved, not cleared,
        so re-checking the instrument restores each child's own prior
        state).
        """
        result = []
        for instrument in self.instruments:
            if not instrument.included:
                continue
            result.extend(g for g in instrument.groups if g.included)
        return result
