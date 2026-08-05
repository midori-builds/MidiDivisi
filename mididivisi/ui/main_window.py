"""
MidiDivisi main window.

Four things only, per current scope:
  1. "Load MusicXML" button -> opens a file dialog, parses the score
  2. Read-only text output area -> shows the parsed articulation
     breakdown per part
  3. "Export MIDI" button -> writes the whole score out as one
     multi-track MIDI file, one track per (instrument, articulation)
     group.
  4. "Export MIDI (Per Instrument)" button -> same grouping, but
     writes one MIDI file per instrument into a chosen folder.
  Both export buttons are disabled until a score has been loaded
  successfully.
"""

import os

from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QPushButton,
    QTextEdit,
    QFileDialog,
)

from mididivisi.core.parser import load_score, get_part_articulation_groups
from mididivisi.core.exporter import (
    export_score_to_midi,
    export_score_to_midi_per_instrument,
)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MidiDivisi")
        self.resize(800, 600)

        # Holds the currently loaded music21 score, and the source
        # file path (used to suggest a sensible export filename).
        # Both are None until a file is loaded successfully.
        self.score = None
        self.loaded_file_path = None

        # --- widgets ---
        self.load_button = QPushButton("Load MusicXML")
        self.load_button.clicked.connect(self.load_musicxml)

        self.export_button = QPushButton("Export MIDI")
        self.export_button.clicked.connect(self.export_midi)
        self.export_button.setEnabled(False)  # nothing loaded yet

        self.export_per_instrument_button = QPushButton(
            "Export MIDI (Per Instrument)"
        )
        self.export_per_instrument_button.clicked.connect(
            self.export_midi_per_instrument
        )
        self.export_per_instrument_button.setEnabled(False)  # nothing loaded yet

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("Parsed data will show up here...")

        # --- layout ---
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self.load_button)
        layout.addWidget(self.export_button)
        layout.addWidget(self.export_per_instrument_button)
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
            score = load_score(file_path)
        except Exception as e:
            self.output.append(f"Failed to parse file: {e}")
            return

        self.score = score
        self.loaded_file_path = file_path
        self.export_button.setEnabled(True)
        self.export_per_instrument_button.setEnabled(True)

        parts = score.parts
        self.output.append(f"Found {len(parts)} part(s):")

        for part in parts:
            # partName is usually set from the instrument/staff name
            # in the MusicXML; fall back if it's missing.
            name = part.partName or "(unnamed part)"
            self.output.append(f"\n{name}")

            groups = get_part_articulation_groups(part)

            if not groups:
                self.output.append("  (no notes found)")
                continue

            for label, notes in sorted(groups.items()):
                self.output.append(f"  - {label}: {len(notes)} note(s)")

    def export_midi(self):
        if self.score is None:
            return  # export button should be disabled in this case anyway

        # Suggest a filename based on the loaded MusicXML file's name.
        default_name = "export.mid"
        if self.loaded_file_path:
            base = os.path.splitext(os.path.basename(self.loaded_file_path))[0]
            default_name = f"{base}.mid"

        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export MIDI",
            default_name,
            "MIDI Files (*.mid)",
        )

        if not save_path:
            return  # user cancelled the dialog

        try:
            export_score_to_midi(self.score, save_path)
        except Exception as e:
            self.output.append(f"\nFailed to export MIDI: {e}")
            return

        self.output.append(f"\nExported MIDI to: {save_path}")

    def export_midi_per_instrument(self):
        if self.score is None:
            return  # export button should be disabled in this case anyway

        output_dir = QFileDialog.getExistingDirectory(
            self,
            "Choose a folder for the exported MIDI files",
        )

        if not output_dir:
            return  # user cancelled the dialog

        try:
            written_paths = export_score_to_midi_per_instrument(
                self.score, output_dir
            )
        except Exception as e:
            self.output.append(f"\nFailed to export MIDI: {e}")
            return

        self.output.append(f"\nExported {len(written_paths)} MIDI file(s) to: {output_dir}")
        for path in sorted(written_paths):
            self.output.append(f"  - {os.path.basename(path)}")
