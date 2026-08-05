"""
Parsing and articulation-detection logic.

Takes a music21 Part and figures out how its notes/chords break down
by articulation and technique, including passage-level techniques
like pizzicato and mute that are encoded as free-text directions
rather than per-note marks.
"""

from music21 import converter

# Free-text technique markings (from MusicXML <words> directions) that
# represent a STATE change applying to all following notes, rather than
# a per-note mark. Text is matched lowercase with trailing periods
# stripped. Extend these sets as more test files surface new wording.
PIZZICATO_ON_WORDS = {"pizz", "pizzicato"}
PIZZICATO_OFF_WORDS = {"arco"}
MUTE_ON_WORDS = {"mute", "muted", "con sord", "con sordino", "sord"}
MUTE_OFF_WORDS = {"senza sord", "senza sordino", "open", "unmuted"}


def load_score(file_path):
    """Parse a MusicXML file and convert it to sounding (concert)
    pitch. Transposing instruments (Clarinet in Bb, Horn in F, etc.)
    store their notes as WRITTEN pitch in MusicXML - without this
    conversion, exported MIDI would play the literal written notes,
    which is wrong for every transposing instrument in the score.
    """
    score = converter.parse(file_path)
    return score.toSoundingPitch()


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
        if cls in ("Tremolo", "Trill"):
            labels.append(cls)

    for sp in n.getSpannerSites():
        if sp.__class__.__name__ == "TremoloSpanner":
            labels.append("TremoloSpanner")

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
