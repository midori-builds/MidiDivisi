"""
MidiDivisi entry point.

Just wires up the QApplication and shows the main window - all real
logic lives in mididivisi/core (parsing) and mididivisi/ui (widgets).
"""

import sys

from PyQt6.QtWidgets import QApplication

from mididivisi.ui.main_window import MainWindow
from mididivisi.ui.theme import build_stylesheet


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(build_stylesheet())
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
