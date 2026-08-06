"""
Parsing and articulation-detection logic.

Takes a music21 Part and figures out how its notes/chords break down
by articulation and technique, including passage-level techniques
like pizzicato and mute that are encoded as free-text directions
rather than per-note marks.
"""

from music21 import converter, key

# Free-text technique markings (from MusicXML <words> directions) that
# represent a STATE change applying to all following notes, rather than
# a per-note mark. Text is matched lowercase with trailing periods
# stripped. Extend these sets as more test files surface new wording.
PIZZICATO_ON_WORDS = {"pizz", "pizzicato"}
PIZZICATO_OFF_WORDS = {"arco"}
MUTE_ON_WORDS = {"mute", "muted", "con sord", "con sordino", "sord"}
MUTE_OFF_WORDS = {"senza sord", "senza sordino", "open", "unmuted"}

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


def load_score(file_path):
    """Parse a MusicXML file, convert it to sounding (concert) pitch,
    and set each note's velocity based on the score's dynamics
    markings. Transposing instruments (Clarinet in Bb, Horn in F,
    etc.) store their notes as WRITTEN pitch in MusicXML - without
    the sounding-pitch conversion, exported MIDI would play the
    literal written notes, which is wrong for every transposing
    instrument in the score.
    """
    score = converter.parse(file_path)
    score = score.toSoundingPitch()

    for part in score.parts:
        apply_dynamics_to_part(part)

    return score


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
    passage-level technique state changes like pizz./arco and
    mute/senza sord. Returns a list of (offset, state_key, is_on)
    events sorted by offset.
    """
    events = []
    for el in part.flatten():
        if el.__class__.__name__ != "TextExpression":
            continue

        text = (el.content or "").strip().lower().rstrip(".")

        if text in PIZZICATO_ON_WORDS:
            events.append((el.offset, "pizzicato", True))
        elif text in PIZZICATO_OFF_WORDS:
            events.append((el.offset, "pizzicato", False))
        elif text in MUTE_ON_WORDS:
            events.append((el.offset, "mute", True))
        elif text in MUTE_OFF_WORDS:
            events.append((el.offset, "mute", False))

    events.sort(key=lambda ev: ev[0])
    return events


def get_part_articulation_groups(part):
    """Walk a part's notes/chords in order, tracking passage-level
    technique state (pizzicato/mute) alongside each note's own
    per-note marks, and return a dict of
    {combined_label: [note_or_chord, ...]}.

    Keeping the actual Note/Chord objects (not just a count) is what
    lets this feed MIDI export later - we need real pitch/offset/
    duration data, not just how many notes matched a label.
    """
    events = get_technique_timeline(part)
    event_index = 0
    state = {"pizzicato": False, "mute": False}
    groups = {}

    for n in part.flatten().notes:
        # Include both single Notes and Chords (double/multi-stops) -
        # they share the same interface for articulations/expressions/
        # spanners, so no separate handling is needed. Skip anything
        # else (e.g. Unpitched percussion - handled separately later).
        if not (n.isNote or n.isChord):
            continue

        # Apply any state-change events that occur at or before this
        # note's offset.
        while event_index < len(events) and events[event_index][0] <= n.offset:
            _, state_key, is_on = events[event_index]
            state[state_key] = is_on
            event_index += 1

        state_labels = []
        if state["pizzicato"]:
            state_labels.append("Pizzicato")
        if state["mute"]:
            state_labels.append("Mute")

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
