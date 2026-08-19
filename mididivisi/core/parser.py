"""
Parsing and articulation-detection logic.

Takes a music21 Part and figures out how its notes/chords break down
by articulation and technique, including passage-level techniques
like pizzicato and mute that are encoded as free-text directions
rather than per-note marks.
"""

import copy

from music21 import converter, interval, key

from mididivisi.core.settings import settings
from mididivisi.core.midifi import MidifiConfig, resolve_tremolo_midifi, MIDIFI_SOURCE_LABEL_PREFIX

# Free-text technique markings (from MusicXML <words> directions) that
# represent a STATE change applying to all following notes, rather than
# a per-note mark. Text is matched lowercase with trailing periods
# stripped. The actual word lists now live in Settings (user-editable,
# persisted to disk) rather than as fixed constants here - see
# settings.py's DEFAULT_KEYWORD_MAPPING for the built-in defaults.
# get_technique_timeline reads settings.get_keyword_set(...) live on
# every call, so an edit made in the Settings dialog takes effect on
# the next file load without needing to restart the app.
#
# Each entry here needs a matching "<key>_on"/"<key>_off" pair in
# Settings' keyword mapping. STATE_KEYWORD_LABELS controls what shows
# up in the combined articulation label (e.g. "SulPont+Staccato").
STATE_KEYWORD_CATEGORIES = [
    "pizzicato",
    "mute",
    "flutter",
    "sul_ponticello",
    "sul_tasto",
    "col_legno",
]

STATE_KEYWORD_LABELS = {
    "pizzicato": "Pizzicato",
    "mute": "Mute",
    "flutter": "Flutter",
    "sul_ponticello": "SulPont",
    "sul_tasto": "SulTasto",
    "col_legno": "ColLegno",
}

# Default velocity mapping for explicit dynamic markings (p, mf, f,
# etc.) now lives in settings.py (DEFAULT_DYNAMIC_VELOCITY_MAP), same
# as the keyword-mapping categories - user-editable, persisted, read
# live via settings.get_dynamic_velocity(). Hairpins (cresc./dim.) are
# NOT interpolated yet - a note inside a written crescendo just keeps
# the last named dynamic's velocity until the next explicit marking.
# See parser.py notes on hairpin spanner fragility for why that's
# deferred rather than attempted now.

# Artificial harmonics are written as a two-note chord: a normal
# notehead (the stopped/fingered pitch) plus a diamond notehead (the
# lightly-touched node) some interval above it. The written chord is
# NOT the sounding pitch - it shows fingering. The actual sounding
# pitch is the stopped note transposed up by a fixed amount that
# depends on the touch interval - each interval corresponds to a
# specific harmonic partial. Verified against multiple independent
# string-technique references (cellofun.eu, handwiki.org,
# conductit.eu). Only these four touch intervals are well documented/
# common enough to trust a formula for - m3 and M3 in particular are
# rare in practice, but do have a real, distinct (non-interchangeable)
# sounding-pitch relationship.
ARTIFICIAL_HARMONIC_TRANSPOSITIONS = {
    "P4": 24,  # 2 octaves above the stopped note (the standard/common case) - exact, 0 cents off equal temperament
    "M3": 28,  # 2 octaves + a major 3rd above the stopped note - ~14 cents flat vs equal temperament (rare in practice)
    "m3": 31,  # 2 octaves + a perfect 5th above the stopped note - ~2 cents sharp vs equal temperament (very rare in practice)
    "P5": 19,  # 1 octave + a perfect 5th (a twelfth) above the stopped note - ~2 cents sharp vs equal temperament
}


def load_score(file_path, midifi_config=None):
    """Parse a MusicXML file, convert it to sounding (concert) pitch,
    resolve artificial harmonics to their real sounding pitch, resolve
    divisi passages, realize eligible single-note tremolo into
    discrete notes per midifi_config, and set each note's velocity
    based on the score's dynamics markings.

    midifi_config defaults to a fresh MidifiConfig() (a true no-op -
    see that class for why) if not given, so existing callers that
    don't care about midi-fy keep working unchanged.

    Transposing instruments (Clarinet in Bb, Horn in F, etc.) store
    their notes as WRITTEN pitch in MusicXML - without the
    sounding-pitch conversion, exported MIDI would play the literal
    written notes, which is wrong for every transposing instrument in
    the score.
    """
    score = converter.parse(file_path)
    score = score.toSoundingPitch()
    config = midifi_config or MidifiConfig()

    for part in score.parts:
        resolve_artificial_harmonics(part)
        resolve_divisi(part)
        resolve_tremolo_midifi(part, config)
        apply_dynamics_to_part(part)

    return score


DEFAULT_TEMPO_BPM = 120


def get_tempo_timeline(score):
    """Scan the WHOLE score (every part, not just one) for tempo
    markings and return a list of (offset, bpm) events, sorted by
    offset, deduplicated by offset. Tempo is score-level, not per-
    instrument - a tempo marking is usually only written on ONE staff
    but applies to the whole piece, so unlike the other timeline
    functions in this module (dynamics, technique state), this
    operates on the Score directly rather than per-Part.

    A MetronomeMark's `.number` (the visible/notated metronome number,
    e.g. an explicit "quarter = 96" marking) is preferred when present;
    `.numberSounding` (the PLAYBACK-only tempo, e.g. from a <sound
    tempo="71"/> attribute attached to a tempo WORD like "Adagio" with
    no explicit metronome number) is used otherwise. Verified this
    distinction directly against real files - relying on `.number`
    alone silently missed real tempo data on files that only have a
    tempo word, not an explicit metronome marking.

    If no tempo marking is found anywhere in the score, a single
    (0, DEFAULT_TEMPO_BPM) event is returned - the exported file is
    always explicit about its tempo rather than depending on
    whatever implicit default a given MIDI reader happens to assume.
    """
    events_by_offset = {}

    for part in score.parts:
        for el in part.flatten():
            if el.__class__.__name__ != "MetronomeMark":
                continue

            bpm = el.number if el.number is not None else el.numberSounding
            if bpm is None:
                continue

            # First one found at a given offset wins - later
            # duplicates (the same tempo re-declared on another staff,
            # or via both a <metronome> element and a <sound tempo>
            # attribute at once, both confirmed to happen in real
            # files) are silently skipped rather than creating
            # redundant/conflicting tempo events at the same tick.
            if el.offset not in events_by_offset:
                events_by_offset[el.offset] = bpm

    if not events_by_offset:
        return [(0, DEFAULT_TEMPO_BPM)]

    return sorted(events_by_offset.items())


def resolve_artificial_harmonics(part):
    """Find chords representing artificial harmonics (a diamond-notehead
    touch pitch + a normal-notehead stopped pitch - the standard string
    notation for this technique) and collapse them to a single note at
    the ACTUAL sounding pitch, tagged so get_note_level_label can label
    it correctly even though the identifying two-pitch shape is gone
    after collapsing.

    Only the three most common, well-documented touch intervals (P4,
    M3, P5 - see ARTIFICIAL_HARMONIC_TRANSPOSITIONS) are corrected. Any
    other touch interval is left as the literal written chord
    (uncorrected pitch) but still tagged/labeled as an artificial
    harmonic, so it stays visible as its own track rather than
    silently blending into a generic Sustain bucket where there'd be
    no indication it needs manual attention.
    """
    for n in part.flatten().notes:
        if not n.isChord or len(n.pitches) != 2:
            continue

        chord_notes = n.notes  # the two constituent Note objects
        diamond_notes = [cn for cn in chord_notes if cn.notehead == "diamond"]
        normal_notes = [cn for cn in chord_notes if cn.notehead != "diamond"]

        if len(diamond_notes) != 1 or len(normal_notes) != 1:
            continue  # not the standard "1 touch + 1 stop" shape

        touched_pitch = diamond_notes[0].pitch
        stopped_pitch = normal_notes[0].pitch

        iv = interval.Interval(stopped_pitch, touched_pitch)
        semitone_shift = ARTIFICIAL_HARMONIC_TRANSPOSITIONS.get(iv.name)

        if semitone_shift is not None:
            sounding_pitch = stopped_pitch.transpose(semitone_shift)
            n.pitches = [sounding_pitch]
        # else: unrecognized touch interval - leave the written chord
        # as-is (uncorrected), but still tag/label it below.

        n.mididivisi_label = "ArtificialHarmonic"


def get_dynamics_timeline(part):
    """Scan a part's explicit Dynamic markings (p, mf, f, etc.) and
    return a list of (offset, velocity) events sorted by offset.
    Velocity values are read live from Settings on every call, same
    as the keyword-mapping categories. Unrecognized dynamic text is
    skipped rather than guessed at.
    """
    events = []
    for el in part.flatten():
        if el.__class__.__name__ != "Dynamic":
            continue

        velocity = settings.get_dynamic_velocity(el.value)
        if velocity is None:
            continue

        events.append((el.offset, velocity))

    events.sort(key=lambda ev: ev[0])
    return events


def apply_dynamics_to_part(part):
    """Walk a part's notes/chords in order and set each one's
    .volume.velocity based on the most recent explicit Dynamic
    marking (a step function - no ramping across hairpins yet).
    Notes before the first marking get the current "mf" velocity from
    Settings (read live, not a value frozen at import time - if the
    user changes mf's velocity in Settings, that default updates too).

    Notes carrying an Accent articulation get the result multiplied by
    settings.accent_velocity_multiplier, clamped to the valid MIDI
    range (0-127). StrongAccent is deliberately EXCLUDED - MusicXML
    has no separate "marcato" element; the marcato "^" symbol IS
    encoded as <strong-accent>/StrongAccent, so treating marcato as
    distinct from plain accents (per design decision) means
    StrongAccent is left out of this entirely, not just Marcato in
    the abstract. See settings.py for the constant's full reasoning.
    This amplification is applied directly to the note data (not
    conditionally based on which Group/Track it later ends up in), so
    it survives regardless of whether the note's accented variant
    later gets merged into its base technique via
    Session.merge_accent_variants.

    This mutates the notes in place (same as toSoundingPitch mutates
    pitch) so every downstream consumer - grouping, export - picks up
    the correct velocity automatically, with no changes needed
    anywhere else in the pipeline.
    """
    events = get_dynamics_timeline(part)
    event_index = 0
    current_velocity = settings.get_dynamic_velocity("mf")

    for n in part.flatten().notes:
        if not (n.isNote or n.isChord):
            continue

        while event_index < len(events) and events[event_index][0] <= n.offset:
            current_velocity = events[event_index][1]
            event_index += 1

        velocity = current_velocity

        articulation_names = {a.__class__.__name__ for a in n.articulations}
        if "Accent" in articulation_names:
            velocity = round(velocity * settings.accent_velocity_multiplier)
            velocity = max(0, min(127, velocity))

        n.volume.velocity = velocity

        # Volume.velocityIsRelative defaults to True, which tells
        # music21's MIDI writer to blend our explicit value with its
        # own internal reading of nearby Dynamic markings (via
        # Volume.getRealized) - effectively double-counting the same
        # dynamic we already used to compute current_velocity.
        # Marking it False makes our calculated value authoritative.
        # Verified directly: without this, a note under an 'f' marking
        # (velocity 96) was actually written to MIDI as 102.
        n.volume.velocityIsRelative = False


def get_note_level_label(n):
    """Build a label describing the per-note articulation/technique
    markings on a single Note or Chord - the ones attached directly to
    that notehead rather than a passage-level state (staccato, accent,
    single/measured tremolo, harmonics, etc.).
    """
    # Artificial harmonics are tagged directly by resolve_artificial_
    # harmonics before this runs, since the chord's pitches have
    # already been collapsed to the sounding pitch by that point - the
    # diamond-notehead shape that would normally identify it is gone.
    override_label = getattr(n, "mididivisi_label", None)
    if override_label:
        return override_label

    labels = []

    for a in n.articulations:
        labels.append(a.__class__.__name__)

    for e in n.expressions:
        cls = e.__class__.__name__
        if cls == "Tremolo":
            labels.append(cls)
        elif cls == "Trill":
            # Interval (whole-step M2 vs half-step m2) isn't written
            # explicitly in MusicXML for a plain trill - it's inferred
            # from the note's pitch and the surrounding key signature,
            # same as a performer reading the score would. Falls back
            # to a plain "Trill" label if inference fails for any
            # reason, rather than crashing the whole parse.
            try:
                key_sig = n.getContextByClass(key.KeySignature)
                size = e.getSize(n, keySig=key_sig)
                labels.append(f"Trill-{size.name}")
            except Exception:
                labels.append("Trill")

    for sp in n.getSpannerSites():
        cls = sp.__class__.__name__
        if cls in ("TremoloSpanner", "Glissando"):
            labels.append(cls)

    seen = []
    for label in labels:
        if label not in seen:
            seen.append(label)

    return "+".join(seen)  # "" if no per-note marks - handled by caller


def get_technique_timeline(part):
    """Scan a part's TextExpressions (from <words> directions) for
    passage-level technique state changes (pizz./arco, mute/senza
    sord., sul pont./ord., etc.). Returns a list of
    (offset, state_key, is_on) events sorted by offset. Word lists are
    read live from Settings on every call.

    Checks EVERY known state category against each TextExpression,
    rather than stopping at the first match - this matters because
    cancel-words genuinely overlap between categories in real
    notation (a single "ord."/"normale" commonly cancels whichever of
    sul ponticello/sul tasto/col legno is currently active, not just
    one specific one). An if/elif chain that stopped at the first
    match would silently leave the others "on" when a shared
    cancel-word appears.
    """
    events = []
    for el in part.flatten():
        if el.__class__.__name__ != "TextExpression":
            continue

        text = (el.content or "").strip().lower().rstrip(".")

        for state_key in STATE_KEYWORD_CATEGORIES:
            on_words = settings.get_keyword_set(f"{state_key}_on")
            off_words = settings.get_keyword_set(f"{state_key}_off")

            if text in on_words:
                events.append((el.offset, state_key, True))
            if text in off_words:
                events.append((el.offset, state_key, False))

    events.sort(key=lambda ev: ev[0])
    return events


def get_divisi_timeline(part):
    """Scan a part's TextExpressions for divisi_on/divisi_off markers
    and return a list of (offset, is_active) events, sorted by
    offset. Kept SEPARATE from get_technique_timeline/
    STATE_KEYWORD_CATEGORIES on purpose - divisi doesn't just add a
    descriptor to existing notes the way pizzicato/mute do, it SPLITS
    them into new derived note-sets (see resolve_divisi), which needs
    fundamentally different downstream handling than simple label
    concatenation.
    """
    return _get_on_off_timeline(part, "divisi_on", "divisi_off")


def get_solo_timeline(part):
    """Scan a part's TextExpressions for solo_on/solo_off markers and
    return a list of (offset, is_active) events. Kept SEPARATE from
    STATE_KEYWORD_CATEGORIES for the same reason as divisi - solo
    isn't "another technique to combine with others" the way
    pizzicato/mute are, it's an orchestration-level ROUTING decision
    (which physical player(s) are playing), the same category as
    divisi, not a label to concatenate onto whatever else a note is
    doing. See get_part_articulation_groups for how this actually
    routes notes to a separate Instrument.
    """
    return _get_on_off_timeline(part, "solo_on", "solo_off")


def _get_on_off_timeline(part, on_key, off_key):
    on_words = settings.get_keyword_set(on_key)
    off_words = settings.get_keyword_set(off_key)

    events = []
    for el in part.flatten():
        if el.__class__.__name__ != "TextExpression":
            continue
        text = (el.content or "").strip().lower().rstrip(".")
        if text in on_words:
            events.append((el.offset, True))
        elif text in off_words:
            events.append((el.offset, False))

    events.sort(key=lambda ev: ev[0])
    return events


def _is_active_at(timeline, offset):
    active = False
    for ev_offset, ev_active in timeline:
        if ev_offset > offset:
            break
        active = ev_active
    return active


def resolve_divisi(part):
    """Detect and split 2-way string-style divisi passages, tagging
    each affected note/chord with a `.mididivisi_divisi_role`
    attribute of "Top", "Bottom", or "Both", for
    get_part_articulation_groups to route into separate tracks.

    Only acts within an explicit divisi_on/divisi_off text window (see
    get_divisi_timeline) - deliberate: a 2-note Chord in a string part
    is structurally IDENTICAL whether it's a genuine divisi passage or
    a double-stop (one player, two strings on their own instrument) -
    the only way to tell them apart is the explicit text marker, so
    requiring it avoids silently misreading a double-stop as a section
    split.

    Two source conventions, both gated by the same text-marker window
    but needing different splitting logic, since they're genuinely
    different music21 data shapes (verified directly against real
    parsed output, not assumed):
      - CHORD-based (div. + a 2-note chord in one voice): one Chord
        object, split by pitch height. The ORIGINAL chord is deep-
        copied first (preserving articulations/expressions on BOTH
        halves), then each copy is mutated down to one pitch and
        tagged Top/Bottom, with the bottom copy inserted at the same
        offset via the original's activeSite - building the bottom
        note from scratch instead was tried first and found (by
        testing a Staccato-marked divisi chord specifically) to
        silently lose the original's articulations on that side only.
      - VOICE-based (two real, independent Voice streams - can have
        completely different rhythms, not just different pitches at
        matching beats): requires comparing two independent timelines,
        not splitting one object. Voice offsets are MEASURE-relative,
        not part-absolute (verified directly - this would have been a
        silent, hard-to-catch bug otherwise) - absolute offset is
        reconstructed as measure.offset + note.offset. Flattening the
        whole part is deliberately NOT used to recover voice identity
        here, since a flattened note's nearest-Voice context is
        unreliable after flattening (verified directly - it returned
        the SAME wrong voice id for every note in a test case).
        Convention: lower voice number = top/stems-up, higher = bottom
        /stems-down (standard engraving practice - an assumption, not
        independently verifiable per note).
    In both cases, an exact (offset, pitch(es), duration) match between
    what would otherwise be Top and Bottom is a unison moment - tagged
    "Both" instead, meaning the note belongs in BOTH resulting tracks
    (get_part_articulation_groups duplicates it), since physically
    both players would be playing it together.

    Scoped to 2-way divisi only, matching real string-writing practice
    - NOT a general N-way splitter and not intended to cover wind/
    brass "a3"/"a4" exploding, which is a different problem (see
    BACKLOG.md's Auto Divisi/Solo section for the reasoning). Anything
    outside 2-way (e.g. an incidental 3+ note chord encountered during
    an active divisi window) is deliberately left untouched rather
    than guessed at.
    """
    timeline = get_divisi_timeline(part)
    if not timeline:
        return  # no divisi markers in this part - nothing to do

    processed_ids = set()

    # --- Pass 1: VOICE-based divisi (measure-level) ---
    for measure in part.getElementsByClass("Measure"):
        voices = list(measure.voices)
        if len(voices) != 2:
            continue  # only the 2-voice case is in scope

        measure_offset = measure.offset
        if not _is_active_at(timeline, measure_offset):
            continue

        v1, v2 = voices[0], voices[1]
        try:
            v1_id, v2_id = int(v1.id), int(v2.id)
        except (TypeError, ValueError):
            v1_id, v2_id = 1, 2  # fallback if voice ids aren't cleanly numeric
        top_voice, bottom_voice = (v1, v2) if v1_id < v2_id else (v2, v1)

        top_notes = [n for n in top_voice.notes if n.isNote or n.isChord]
        bottom_notes = [n for n in bottom_voice.notes if n.isNote or n.isChord]

        def _note_key(n):
            pitches = tuple(sorted(p.midi for p in n.pitches)) if n.isChord else (n.pitch.midi,)
            return (measure_offset + n.offset, pitches, n.duration.quarterLength)

        bottom_by_key = {_note_key(n): n for n in bottom_notes}
        matched_keys = set()

        for n in top_notes:
            key = _note_key(n)
            if key in bottom_by_key:
                # Only the TOP note gets tagged "Both" -
                # get_part_articulation_groups duplicates every "Both"
                # -tagged note into both Top and Bottom groups on its
                # own. Tagging BOTH the top and bottom objects here
                # (tried first) meant each independently triggered
                # that duplication, producing FOUR entries for one
                # genuine unison event instead of two - caught by
                # testing a real two-measure voice-based divisi
                # passage, not visible from a single-measure test.
                # The bottom note's musical content is now fully
                # represented by the top note's tag, so it's removed
                # from the stream entirely rather than also tagged.
                n.mididivisi_divisi_role = "Both"
                matching_bottom = bottom_by_key[key]
                bottom_site = matching_bottom.activeSite
                if bottom_site is not None:
                    bottom_site.remove(matching_bottom)
                matched_keys.add(key)
            else:
                n.mididivisi_divisi_role = "Top"
            processed_ids.add(id(n))

        for n in bottom_notes:
            key = _note_key(n)
            if key not in matched_keys:
                n.mididivisi_divisi_role = "Bottom"
            processed_ids.add(id(n))

    # --- Pass 2: CHORD-based divisi (note-level) ---
    # Anything already handled by the voice pass above is skipped, so
    # a measure that used real voices doesn't get double-processed
    # here.
    for n in list(part.flatten().notes):
        if id(n) in processed_ids:
            continue
        if not (n.isNote or n.isChord):
            continue
        if not _is_active_at(timeline, n.offset):
            continue

        if n.isNote:
            # A single pitch during an active divisi window - both
            # players are playing this note together.
            n.mididivisi_divisi_role = "Both"
        elif n.isChord and len(n.pitches) == 2:
            top_pitch = max(n.pitches, key=lambda p: p.midi)
            bottom_pitch = min(n.pitches, key=lambda p: p.midi)

            if top_pitch.midi == bottom_pitch.midi:
                # A "chord" whose two notated pitches are actually the
                # same pitch - already a unison, not a real split.
                n.pitches = [top_pitch]
                n.mididivisi_divisi_role = "Both"
                continue

            site = n.activeSite
            # Deep-copy the WHOLE original chord before mutating
            # either half - this is what preserves articulations/
            # expressions/etc. on BOTH resulting notes symmetrically.
            # Building the bottom note from scratch (note.Note(...))
            # was tried first and found to silently lose the original
            # chord's articulations on that side only, since a fresh
            # Note object starts with an empty articulations list -
            # caught by testing a Staccato-marked divisi chord
            # specifically, not found by inspection alone.
            bottom_chord = copy.deepcopy(n)
            bottom_chord.pitches = [bottom_pitch]
            bottom_chord.mididivisi_divisi_role = "Bottom"

            n.pitches = [top_pitch]
            n.mididivisi_divisi_role = "Top"

            if site is not None:
                site.insert(n.offset, bottom_chord)
        # else: 1 or 3+ pitches - out of scope, left untouched (no tag)


def get_part_articulation_groups(part):
    """Walk a part's notes/chords in order, tracking passage-level
    technique state (see STATE_KEYWORD_CATEGORIES) alongside each
    note's own per-note marks, and return a dict of
    {(routing, combined_label): [note_or_chord, ...]}.

    `routing` is None (normal/tutti), "DivisiTop", "DivisiBottom", or
    "Solo" - a SEPARATE dimension from the articulation label, on
    purpose: routing answers "which physical player(s) are playing
    this," while the label answers "what technique are they using" -
    two genuinely different questions that used to be conflated into
    one combined string (e.g. "DivisiTop+Staccato"), which turned out
    to be a real problem (see Session.from_score() / BACKLOG.md's
    Divisi section for why - keyword-matching a Profile against that
    combined string meant divisi/solo passages could accidentally get
    swept into keyswitch-flattening if a user ever typed the exact
    combined label). Session.from_score() uses `routing` to build
    genuinely SEPARATE Instruments, not just separate Groups.

    Divisi routing (from resolve_divisi's per-note tagging) takes
    priority over solo (mutually exclusive in real orchestration
    anyway - divisi implies multiple players, solo implies one).

    Keeping the actual Note/Chord objects (not just a count) is what
    lets this feed MIDI export later - we need real pitch/offset/
    duration data, not just how many notes matched a label.
    """
    events = get_technique_timeline(part)
    event_index = 0
    state = {key: False for key in STATE_KEYWORD_CATEGORIES}
    groups = {}

    solo_timeline = get_solo_timeline(part)

    for n in part.flatten().notes:
        # Include both single Notes and Chords (double/multi-stops) -
        # they share the same interface for articulations/expressions/
        # spanners, so no separate handling is needed. Skip anything
        # else (e.g. Unpitched percussion - handled separately later).
        if not (n.isNote or n.isChord):
            continue

        # Apply any state-change events that occur at or before this
        # note's offset. Multiple events can share an offset (e.g. one
        # "ord." cancelling two active states at once).
        while event_index < len(events) and events[event_index][0] <= n.offset:
            _, state_key, is_on = events[event_index]
            state[state_key] = is_on
            event_index += 1

        state_labels = [
            STATE_KEYWORD_LABELS[key] for key in STATE_KEYWORD_CATEGORIES if state[key]
        ]

        note_label = get_note_level_label(n)

        # If the only per-note marking present is Accent/StrongAccent
        # with no other technique, make the base explicit as
        # "Sustain+Accent" rather than leaving it as bare "Accent" -
        # for consistency with every other combination, which already
        # shows the base technique alongside the accent (e.g.
        # "Staccato+Accent"). Applies to StrongAccent too, same
        # reasoning.
        if note_label:
            note_label_parts = note_label.split("+")
            if all(p in ("Accent", "StrongAccent") for p in note_label_parts):
                note_label = "+".join(["Sustain"] + note_label_parts)

        base_label_parts = state_labels + ([note_label] if note_label else [])
        base_label = "+".join(base_label_parts) if base_label_parts else "Sustain"

        # Midi-fy routing: a note realized from a tremolo (or, later,
        # other midi-fy sources) gets a distinguishable
        # "Midifi+<base_label>" label rather than merging silently
        # into whatever base_label it would otherwise get - this is
        # what makes Session.merge_midifi_variants possible (auto-
        # merge into the matching base bucket, e.g. "Spiccato", with
        # full split-reversibility), same non-destructive pattern
        # already used for Merge Accents. A generic label PREFIX (not
        # a separate routing dimension like divisi/solo) is
        # deliberate here - unlike divisi/solo, midi-fied notes should
        # end up combined with the REST of the SAME instrument's
        # matching articulation, not become their own instrument.
        if getattr(n, "mididivisi_midifi_source", None) is not None:
            base_label = f"{MIDIFI_SOURCE_LABEL_PREFIX}+{base_label}"

        # Divisi routing - see resolve_divisi for how notes get tagged
        # with .mididivisi_divisi_role. "Both" (a unison moment within
        # an active divisi passage) goes into BOTH resulting
        # instruments, duplicated via deepcopy rather than sharing one
        # object reference across two independently-owned note lists.
        divisi_role = getattr(n, "mididivisi_divisi_role", None)

        if divisi_role == "Both":
            groups.setdefault(("DivisiTop", base_label), []).append(n)
            # deepcopy does NOT reliably preserve absolute offset for a
            # note nested in Voice/Measure structure - verified
            # directly (a real note at offset 2.0 came back as 0.0
            # after copying). Explicitly re-set from the original
            # rather than trust the copy - same safe pattern already
            # used elsewhere (exporter.py's _build_midi_track reads
            # n.offset from the ORIGINAL note at insert time, not from
            # whatever a copy's own .offset attribute reports).
            duplicate = copy.deepcopy(n)
            duplicate.offset = n.offset
            groups.setdefault(("DivisiBottom", base_label), []).append(duplicate)
        elif divisi_role == "Top":
            groups.setdefault(("DivisiTop", base_label), []).append(n)
        elif divisi_role == "Bottom":
            groups.setdefault(("DivisiBottom", base_label), []).append(n)
        elif _is_active_at(solo_timeline, n.offset):
            groups.setdefault(("Solo", base_label), []).append(n)
        else:
            groups.setdefault((None, base_label), []).append(n)

    return groups


def get_part_articulation_counts(part):
    """Same grouping as get_part_articulation_groups, but returns just
    {(routing, label): count} - kept for the console-output view,
    which only needs counts, not the underlying note objects.
    """
    groups = get_part_articulation_groups(part)
    return {key: len(notes) for key, notes in groups.items()}
