"""
MidiDivisi - minimal UI shell.

Step 1: load a MusicXML file with music21 and print basic part
info (how many parts, their names) into the text output area.
No articulation extraction yet - that's the next step.
"""

import sys

from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QPushButton,
    QTextEdit,
    QFileDialog,
)

from music21 import converter


# Free-text technique markings (from MusicXML <words> directions) that
# represent a STATE change applying to all following notes, rather than
# a per-note mark. Text is matched lowercase with trailing periods
# stripped. Extend these sets as more test files surface new wording.
PIZZICATO_ON_WORDS = {"pizz", "pizzicato"}
PIZZICATO_OFF_WORDS = {"arco"}
MUTE_ON_WORDS = {"mute", "muted", "con sord", "con sordino", "sord"}
MUTE_OFF_WORDS = {"senza sord", "senza sordino", "open", "unmuted"}


def get_note_level_label(n):
    """Build a label describing the per-note articulation/technique
    markings on a single Note - the ones attached directly to that
    notehead rather than a passage-level state (staccato, accent,
    single/measured tremolo, harmonics, etc.).
    """
    labels = []

    for a in n.articulations:
        labels.append(a.__class__.__name__)

    for e in n.expressions:
        if e.__class__.__name__ == "Tremolo":
            labels.append("Tremolo")

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


def get_part_articulation_counts(part):
    """Walk a part's notes in order, tracking passage-level technique
    state (pizzicato/mute) alongside each note's own per-note marks,
    and return a dict of {combined_label: note_count}.
    """
    events = get_technique_timeline(part)
    event_index = 0
    state = {"pizzicato": False, "mute": False}
    counts = {}

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

        counts[label] = counts.get(label, 0) + 1

    return counts


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MidiDivisi")
        self.resize(800, 600)

        # --- widgets ---
        self.load_button = QPushButton("Load MusicXML")
        self.load_button.clicked.connect(self.load_musicxml)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("Parsed data will show up here...")

        # --- layout ---
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self.load_button)
        layout.addWidget(self.output)
        self.setCentralWidget(central)

    def load_musicxml(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load MusicXML",
            "",
            "MusicXML Files (*.xml *.musicxml *.mxl);;All Files (*)",
        )

        if not file_path:
            return  # user cancelled the dialog

        self.output.append(f"Loaded file: {file_path}")

        try:
            score = converter.parse(file_path)
        except Exception as e:
            self.output.append(f"Failed to parse file: {e}")
            return

        parts = score.parts
        self.output.append(f"Found {len(parts)} part(s):")

        for part in parts:
            # partName is usually set from the instrument/staff name
            # in the MusicXML; fall back if it's missing.
            name = part.partName or "(unnamed part)"
            self.output.append(f"\n{name}")

            # Chords are skipped for now - we're only handling single
            # Note objects in this pass.
            counts = get_part_articulation_counts(part)

            if not counts:
                self.output.append("  (no notes found)")
                continue

            for label, count in sorted(counts.items()):
                self.output.append(f"  - {label}: {count} note(s)")


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
