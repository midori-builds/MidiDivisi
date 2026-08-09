"""
Parsing and articulation-detection logic.

Takes a music21 Part and figures out how its notes/chords break down
by articulation and technique, including passage-level techniques
like pizzicato and mute that are encoded as free-text directions
rather than per-note marks.
"""

from music21 import converter, interval, key

from mididivisi.core.settings import settings

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
# etc.). This is a first-pass global default - no per-library
# profiles or user overrides yet (planned for a future settings
# dialog alongside sample-library profiles). Hairpins (cresc./dim.)
# are NOT interpolated yet - a note inside a written crescendo just
# keeps the last named dynamic's velocity until the next explicit
# marking. See parser.py notes on hairpin spanner fragility for why
# that's deferred rather than attempted now.
DYNAMIC_VELOCITY_MAP = {
    "ppp": 16,
    "pp": 33,
    "p": 49,
    "mp": 64,
    "mf": 80,
    "f": 96,
    "ff": 112,
    "fff": 127,
}

DEFAULT_VELOCITY = DYNAMIC_VELOCITY_MAP["mf"]

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


def load_score(file_path):
    """Parse a MusicXML file, convert it to sounding (concert) pitch,
    resolve artificial harmonics to their real sounding pitch, and set
    each note's velocity based on the score's dynamics markings.

    Transposing instruments (Clarinet in Bb, Horn in F, etc.) store
    their notes as WRITTEN pitch in MusicXML - without the
    sounding-pitch conversion, exported MIDI would play the literal
    written notes, which is wrong for every transposing instrument in
    the score.
    """
    score = converter.parse(file_path)
    score = score.toSoundingPitch()

    for part in score.parts:
        resolve_artificial_harmonics(part)
        apply_dynamics_to_part(part)

    return score


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
    Unrecognized dynamic text (not in DYNAMIC_VELOCITY_MAP) is
    skipped rather than guessed at.
    """
    events = []
    for el in part.flatten():
        if el.__class__.__name__ != "Dynamic":
            continue

        velocity = DYNAMIC_VELOCITY_MAP.get(el.value)
        if velocity is None:
            continue

        events.append((el.offset, velocity))

    events.sort(key=lambda ev: ev[0])
    return events


def apply_dynamics_to_part(part):
    """Walk a part's notes/chords in order and set each one's
    .volume.velocity based on the most recent explicit Dynamic
    marking (a step function - no ramping across hairpins yet).
    Notes before the first marking get DEFAULT_VELOCITY.

    This mutates the notes in place (same as toSoundingPitch mutates
    pitch) so every downstream consumer - grouping, export - picks up
    the correct velocity automatically, with no changes needed
    anywhere else in the pipeline.
    """
    events = get_dynamics_timeline(part)
    event_index = 0
    current_velocity = DEFAULT_VELOCITY

    for n in part.flatten().notes:
        if not (n.isNote or n.isChord):
            continue

        while event_index < len(events) and events[event_index][0] <= n.offset:
            current_velocity = events[event_index][1]
            event_index += 1

        n.volume.velocity = current_velocity

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


def get_part_articulation_groups(part):
    """Walk a part's notes/chords in order, tracking passage-level
    technique state (see STATE_KEYWORD_CATEGORIES) alongside each
    note's own per-note marks, and return a dict of
    {combined_label: [note_or_chord, ...]}.

    Keeping the actual Note/Chord objects (not just a count) is what
    lets this feed MIDI export later - we need real pitch/offset/
    duration data, not just how many notes matched a label.
    """
    events = get_technique_timeline(part)
    event_index = 0
    state = {key: False for key in STATE_KEYWORD_CATEGORIES}
    groups = {}

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

        if note_label:
            label = "+".join(state_labels + [note_label])
        elif state_labels:
            label = "+".join(state_labels)
        else:
            label = "Sustain"

        groups.setdefault(label, []).append(n)

    return groups


def get_part_articulation_counts(part):
    """Same grouping as get_part_articulation_groups, but returns just
    {label: count} - kept for the console-output view, which only
    needs counts, not the underlying note objects.
    """
    groups = get_part_articulation_groups(part)
    return {label: len(notes) for label, notes in groups.items()}
