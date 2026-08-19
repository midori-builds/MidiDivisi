"""
Midi-fy: generating/manipulating real, discrete MIDI note events from
a notated technique - a genuinely different category from everything
else in this app so far, which only relabels/regroups EXISTING notes
(state timelines, articulation labels) rather than producing new
timing/pitch data. Tremolo is the first concrete feature built on
this; more (tremolo spanners, glissando, legato) are planned to share
the same underlying shape - see BACKLOG.md's "Note-transformation
features" section for the full roadmap.

Unlike the other note-mutation passes in parser.py (artificial
harmonics, divisi), midi-fy is NOT a fixed, automatic part of every
load - its parameters are per-invocation and user-controlled via a
dedicated tool, not a global Settings default (the right tremolo
threshold genuinely depends on the piece - a 3-flag tremolo means
something different in a slow piece than a fast one, per design
discussion). See MidifiConfig for how this gets threaded through.

Chosen strategy for applying a CHANGED config: full session rebuild
(re-parse from the original file with the new config), not surgically
patching an already-loaded session's notes in place - consistent with
how this project already handles Profile reapplication and Settings
changes (always rebuild clean from source, never incrementally patch)
and simpler to reason about, at the cost of discarding in-session-only
manual customization on rebuild, a tradeoff already accepted
elsewhere, not a new one.
"""

import copy

MIDIFI_SOURCE_LABEL_PREFIX = "Midifi"


class MidifiConfig:
    """Holds all midi-fy feature parameters for one Session. Lives on
    Session.midifi_config, persists through save/load (same pattern as
    Session.tempo_events), and is what a rebuild re-applies in full -
    every rebuild reapplies the WHOLE current config together, not
    just whichever single setting was most recently changed, so
    opening one midi-fy tool can never silently discard another's
    configuration once more than one midi-fy feature exists.
    """

    def __init__(self):
        # Tremolo flag count at/above which a single-note tremolo
        # stays "unmeasured" (untouched - exported as a plain
        # sustained note for a dedicated tremolo patch) rather than
        # being realized into literal discrete repeated notes.
        # Default 1 (the lowest real flag count a tremolo can have)
        # means EVERY tremolo counts as unmeasured - i.e. midi-fy has
        # NO effect until the user explicitly raises this,
        # deliberately matching "identical to current behavior" as
        # the default rather than needing a separate on/off flag.
        self.tremolo_min_unmeasured_flags = 1

    def to_dict(self):
        return {"tremolo_min_unmeasured_flags": self.tremolo_min_unmeasured_flags}

    @classmethod
    def from_dict(cls, data):
        config = cls()
        config.tremolo_min_unmeasured_flags = data.get("tremolo_min_unmeasured_flags", 1)
        return config


def resolve_tremolo_midifi(part, config):
    """Realize single-note tremolo (expressions.Tremolo - NOT
    TremoloSpanner, the two-pitch alternating case, which is always
    measured by definition and explicitly out of scope here) into
    literal discrete repeated notes, for any tremolo whose flag count
    is BELOW config.tremolo_min_unmeasured_flags.

    A tremolo with N marks always becomes 2**N notes of equal
    duration, evenly dividing the original note's total duration -
    matches standard practice regardless of the written note's own
    value (verified directly against the original real-world example
    that motivated this feature: an eighth note with 1 mark becomes
    two 16th notes, math confirmed before relying on it).

    Only applies to plain Notes, not Chords - even though a Chord
    could theoretically carry a Tremolo expression (e.g. a tremolo
    chord in piano writing), that's outside the specific ambiguity
    this feature exists to resolve (the single-repeated-pitch
    measured-vs-buzz question), so it's deliberately left untouched
    rather than guessed at - same "stay within defined scope" pattern
    already used for divisi's 2-pitch-only chord restriction.

    Resulting notes are tagged .mididivisi_midifi_source = "tremolo"
    so get_part_articulation_groups can give them a distinguishable
    "Midifi+..." label - auto-mergeable into their base articulation
    bucket via Session.merge_midifi_variants, with full split-
    reversibility (same non-destructive pattern already used for
    Merge Accents) - rather than staying grouped as "Tremolo" forever,
    which would defeat the whole point (per the concrete motivating
    example: a spiccato passage with an occasional tremolo-marked note
    should end up looking like every other spiccato note, not stuck in
    its own separate track).

    Mutation approach (deep-copy the WHOLE original note before
    stripping/mutating, insert the rest via activeSite, explicitly
    re-set offset on each copy) reuses the exact pattern already
    proven correct for divisi's chord-splitting - including the two
    real lessons learned there: deepcopy alone doesn't reliably
    preserve absolute offset for notes in complex stream structures,
    and building a decorated note from scratch (rather than copying
    the original) risks silently losing its other articulations.
    """
    for n in list(part.flatten().notes):
        if not n.isNote:
            continue

        tremolo_exprs = [e for e in n.expressions if e.__class__.__name__ == "Tremolo"]
        if not tremolo_exprs:
            continue

        num_marks = tremolo_exprs[0].numberOfMarks
        if num_marks is None or num_marks >= config.tremolo_min_unmeasured_flags:
            continue  # stays unmeasured, untouched

        site = n.activeSite
        if site is None:
            continue

        num_notes = 2**num_marks
        each_duration = n.quarterLength / num_notes
        original_offset = n.offset

        # Insert every NEW note FIRST, and only mutate the ORIGINAL
        # note's own duration LAST, after all insertions are done -
        # kept as a defensive ordering choice. While tracking down an
        # earlier test failure, mutating an already-sited Note's
        # .duration before further site.insert() calls appeared to
        # corrupt the site - but that turned out to be an artifact of
        # an unrealistic bare stream.Part() test setup (no Measure
        # nesting), not a real issue: re-verified against genuinely
        # parsed MusicXML (real Measure structure, matching how this
        # app always actually loads files) and the ordering made no
        # difference there. Left in this order anyway since it costs
        # nothing and there wasn't time to fully root-cause the
        # original artifact.
        for i in range(1, num_notes):
            new_note = copy.deepcopy(n)
            new_note.expressions = [
                e for e in new_note.expressions if e.__class__.__name__ != "Tremolo"
            ]
            new_note.duration.quarterLength = each_duration
            new_note.mididivisi_midifi_source = "tremolo"
            new_offset = original_offset + i * each_duration
            site.insert(new_offset, new_note)

        n.expressions = [e for e in n.expressions if e.__class__.__name__ != "Tremolo"]
        n.mididivisi_midifi_source = "tremolo"
        n.duration.quarterLength = each_duration
