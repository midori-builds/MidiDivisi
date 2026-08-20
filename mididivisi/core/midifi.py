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

from music21 import converter

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
        # Default 3, matching real notational convention (1-2 flags
        # conventionally means precise rhythmic subdivision, 3+
        # conventionally means "as fast as possible"/buzz effect) -
        # still fully user-adjustable per session, since the right
        # threshold genuinely depends on the piece (a slow adagio can
        # legitimately want even a 3-flag tremolo treated as measured
        # instead).
        self.tremolo_min_unmeasured_flags = 3

        # Trill alternation rate, expressed as notes-per-quarter-note
        # (a TEMPO-RELATIVE subdivision, not an absolute Hz value) -
        # matches how trills are actually notated, an ornament
        # relative to the beat, so this stays musically correct across
        # tempo changes within a piece rather than needing to. Default
        # 8 = a 32nd-note-rate alternation, a reasonable general-
        # purpose starting point - real rate/shape/curve controls are
        # still being designed (see BACKLOG.md), this is deliberately
        # just the one parameter being tackled first.
        self.trill_notes_per_quarter = 8

    def to_dict(self):
        return {
            "tremolo_min_unmeasured_flags": self.tremolo_min_unmeasured_flags,
            "trill_notes_per_quarter": self.trill_notes_per_quarter,
        }

    @classmethod
    def from_dict(cls, data):
        config = cls()
        # Fallback of 1 here is DELIBERATELY different from the
        # constructor's own default (3) - this path is specifically
        # for loading an OLD saved session that predates this feature
        # entirely (no "midifi_config" key at all), and such a session
        # genuinely had NO midi-fy applied when it was saved. Falling
        # back to 3 here would silently start realizing tremolo in a
        # file that never had that happen, the first time it's
        # reopened - falling back to 1 (the true "nothing happens"
        # value) correctly reconstructs the same state the session
        # actually had.
        config.tremolo_min_unmeasured_flags = data.get("tremolo_min_unmeasured_flags", 1)
        # Trill rate does NOT need the same deliberately-different-
        # fallback treatment tremolo needed above: trill realization
        # is toggled per-note, on demand (see the non-destructive
        # architecture design in BACKLOG.md) - an old session has no
        # trills toggled on regardless of what rate value is present,
        # so there's no "silently changes already-reconstructed note
        # data" risk the way tremolo's session-wide, always-applied
        # threshold has. Safe to just fall back to the same default
        # the constructor uses.
        config.trill_notes_per_quarter = data.get(
            "trill_notes_per_quarter", cls().trill_notes_per_quarter
        )
        return config


def realize_trill_notes(main_pitch_midi, upper_pitch_midi, total_duration, notes_per_quarter):
    """PURE function - no music21 stream/context dependency at all,
    deliberately, so it can be reused later for on-demand realization
    (compute fresh each time a trill's toggle is switched on, rather
    than baked in once at parse time - see the non-destructive
    architecture design in BACKLOG.md) without needing to worry about
    whether the originating note is still attached to its original
    stream.

    Given a trill's main pitch and upper-auxiliary pitch (as plain
    MIDI note numbers, not music21 Pitch objects - keeps this function
    free of any music21 dependency at all), the total duration to
    fill (in quarterLength), and a rate (alternating notes per quarter
    note - a TEMPO-RELATIVE subdivision, not an absolute Hz value, so
    the same rate value stays musically correct regardless of the
    piece's actual tempo), returns a list of (pitch_midi, offset,
    duration) tuples for the alternating trill notes.

    Alternation starts on the MAIN pitch, not the upper auxiliary -
    the modern/common performance-practice convention. (Some
    historical/baroque convention starts on the upper note instead;
    picked the modern convention as the MVP default since it's more
    common in general practice, not because the alternative is wrong -
    flagged as adjustable if this doesn't match what's actually
    wanted once heard.)

    Duration-fit: evenly divides total_duration across however many
    notes the rate implies (rounded to a whole number, minimum 2 so an
    actual alternation occurs), rather than hitting the target rate
    exactly and leaving a leftover fractional gap. Mirrors tremolo's
    already-proven approach (evenly dividing duration, not leaving
    remainders) - picked as the simpler, more robust MVP default for
    a question BACKLOG.md flagged as still genuinely open: this makes
    note count and total duration always exact, at the cost of the
    ACTUAL rate being slightly approximate depending on how evenly the
    target count divides the total duration.
    """
    if total_duration <= 0 or notes_per_quarter <= 0:
        return []

    target_count = round(total_duration * notes_per_quarter)
    note_count = max(2, target_count)

    each_duration = total_duration / note_count

    result = []
    for i in range(note_count):
        pitch = main_pitch_midi if i % 2 == 0 else upper_pitch_midi
        offset = i * each_duration
        result.append((pitch, offset, each_duration))

    return result


def realize_tremolo_spanner_notes(first_pitches_midi, second_pitches_midi, total_duration, number_of_marks):
    """PURE function - given the two SIDES of a measured tremolo
    spanner (each a list of MIDI pitch numbers - a single-element list
    for a plain note, multiple for a chord), the total duration to
    fill, and the tremolo's flag count, returns a list of
    (pitches_tuple, offset, duration) for the ON-state realization:
    alternating between the two sides for 2^number_of_marks total
    slots, evenly dividing the duration.

    Reuses the SAME "N flags -> 2^N notes" relationship already
    proven for single-note tremolo (resolve_tremolo_midifi below),
    just applied to a spanner's combined duration instead of one
    note's duration - and generalized to a LIST of simultaneous
    pitches per slot rather than a single pitch, so a note-to-note and
    a chord-to-chord tremolo (even with mismatched note counts on each
    side) are both handled by this one function.

    Deliberately no external rate parameter, unlike trill - flag count
    directly and unambiguously determines the count here, there's no
    speed ambiguity to solve the way trill's realization needed one.
    """
    if total_duration <= 0 or number_of_marks <= 0:
        return []

    note_count = 2 ** number_of_marks
    each_duration = total_duration / note_count

    result = []
    for i in range(note_count):
        pitches = first_pitches_midi if i % 2 == 0 else second_pitches_midi
        offset = i * each_duration
        result.append((tuple(pitches), offset, each_duration))

    return result


def collapse_tremolo_spanner_to_base(first_pitches_midi, total_duration):
    """PURE function - the OFF-state (default) transformation for a
    measured tremolo spanner: ONE sustained note/chord at the FIRST-
    WRITTEN side's pitch(es), spanning the tremolo's full duration.

    Deliberately its own named, testable unit rather than an inline
    one-liner - unlike trill (where "off" just means "return the
    untouched original," nothing to compute), tremolo spanner's off
    state IS a real transformation, replacing the old placeholder
    (which kept the original written rhythm, producing multiple same-
    pitch note-on events that would re-trigger a sustained patch mid-
    phrase unnecessarily). One note-on/note-off pair instead, letting
    a dedicated tremolo/roll patch handle the passage uninterrupted.
    """
    if total_duration <= 0:
        return []
    return [(tuple(first_pitches_midi), 0, total_duration)]


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


def detect_midifiable_content(file_path):
    """Scan a MusicXML file for content that midi-fy could apply to,
    entirely independent of any midi-fy config or processing - a
    lightweight pre-check used for the "this score has tremolo, check
    Midi-fy" notice shown on import, not a processing decision itself.

    Does its OWN minimal parse (convert to sounding pitch only, no
    harmonics/divisi/midifi resolution) rather than reusing
    load_score() - deliberately, to count RAW, unprocessed tremolo
    markings before any realization could have already split one
    original event into several notes. Counting on an
    already-processed score would either over-count (a single
    tremolo split into 8 realized notes looking like 8 "hits") or
    under-count depending on what the active config already decided,
    neither of which is what this notice needs - it just needs to
    know whether the score has tremolo content at all.

    Returns {"tremolo": count} - extensible for future midi-fy feature
    types (e.g. "glissando") without needing to redesign this
    function's shape. Empty dict if nothing found.
    """
    score = converter.parse(file_path)
    score = score.toSoundingPitch()

    counts = {"tremolo": 0}
    for part in score.parts:
        for n in part.flatten().notes:
            if n.isNote and any(e.__class__.__name__ == "Tremolo" for e in n.expressions):
                counts["tremolo"] += 1

    return {k: v for k, v in counts.items() if v > 0}
