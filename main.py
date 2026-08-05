"""
MidiDivisi
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

        # Placeholder output for now - parsing logic comes next.
        self.output.append(f"Loaded file: {file_path}")


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
