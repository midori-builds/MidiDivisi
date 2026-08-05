"""
MidiDivisi main window.

Two things only, per current scope:
  1. "Load MusicXML" button -> opens a file dialog
  2. Read-only text output area -> shows the parsed articulation
     breakdown per part
"""

from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QPushButton,
    QTextEdit,
    QFileDialog,
)

from music21 import converter

from mididivisi.core.parser import get_part_articulation_counts


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

            counts = get_part_articulation_counts(part)

            if not counts:
                self.output.append("  (no notes found)")
                continue

            for label, count in sorted(counts.items()):
                self.output.append(f"  - {label}: {count} note(s)")
