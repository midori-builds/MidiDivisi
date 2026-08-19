"""
Midi-fy tool dialog.

Deliberately a STANDALONE tool, not a Settings page - the right
tremolo threshold genuinely depends on the piece (a 3-flag tremolo
means something different in a slow piece than a fast one), so this
is per-song configuration, not a global default (see design
discussion in BACKLOG.md's Note-transformation features section).

Applying a change here triggers a FULL SESSION REBUILD (re-parse the
original file with the new config) - the chosen strategy, consistent
with how this app already handles Profile reapplication and other
"always rebuild clean from source" operations. This means any manual
merges/renames/etc. done since the file was loaded get DISCARDED - the
same tradeoff already accepted elsewhere, not a new one, but real
enough to warrant a confirmation before doing it.
"""

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QPushButton,
    QMessageBox,
)

from mididivisi.core.midifi import MidifiConfig


class MidifiDialog(QDialog):
    def __init__(self, current_config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Midi-fy")
        self.resize(480, 220)

        self.result_config = None  # set by _apply() if the user confirms

        layout = QVBoxLayout(self)

        # --- Tremolo section (first midi-fy feature; more planned) ---
        layout.addWidget(QLabel("<b>Tremolo</b>"))

        intro = QLabel(
            "A single-note tremolo with FEWER flags than this threshold gets "
            "realized into literal repeated notes (e.g. 1 flag \u2192 2 notes, "
            "2 flags \u2192 4 notes). At or above this threshold, it stays a "
            "single sustained note for a dedicated tremolo patch."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        threshold_row = QHBoxLayout()
        threshold_row.addWidget(QLabel("Minimum flags for unmeasured tremolo:"))

        self.threshold_spin = QSpinBox()
        self.threshold_spin.setRange(1, 8)
        self.threshold_spin.setValue(current_config.tremolo_min_unmeasured_flags)
        self.threshold_spin.setFixedSize(90, 28)
        threshold_row.addWidget(self.threshold_spin)

        threshold_row.addStretch(1)
        layout.addLayout(threshold_row)

        layout.addStretch(1)

        # --- Buttons ---
        button_row = QHBoxLayout()
        button_row.addStretch(1)

        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_row.addWidget(cancel_button)

        apply_button = QPushButton("Apply")
        apply_button.clicked.connect(self._apply)
        button_row.addWidget(apply_button)

        layout.addLayout(button_row)

    def _apply(self):
        confirmed = QMessageBox.question(
            self,
            "Rebuild session?",
            "Applying this will rebuild the session from the original "
            "score file with the new setting - any manual merges, "
            "renames, or other changes made since the file was loaded "
            "will be discarded. Continue?",
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.Cancel,
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return

        new_config = MidifiConfig()
        new_config.tremolo_min_unmeasured_flags = self.threshold_spin.value()
        self.result_config = new_config
        self.accept()
