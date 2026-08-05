"""
MidiDivisi - minimal UI shell.
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
            note_count = len(part.flatten().notes)
            self.output.append(f"  - {name}: {note_count} note(s)")


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
