"""
MidiDivisi entry point
"""

import sys

from PyQt6.QtWidgets import QApplication

from mididivisi.ui.main_window import MainWindow # type: ignore


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
