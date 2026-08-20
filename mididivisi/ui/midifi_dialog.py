"""
Midi-fy tool dialog.

Deliberately a STANDALONE tool, not a Settings page - the right
tremolo threshold and trill rate genuinely depend on the piece, so
this is per-song configuration, not a global default (full reasoning
in DEVLOG.md).

Applying a change here does NOT uniformly do the same thing for every
setting - tremolo requires a full session rebuild (destructive, parse-
time realization), trill rate applies instantly (computed fresh on
demand, no rebuild needed). _apply() compares old vs. new values to
decide which path applies, rather than the caller needing to know the
difference. Full reasoning in DEVLOG.md - kept OUT of the UI itself
deliberately: this dialog should read like a tool, not a manual.
"""

from PyQt6.QtCore import Qt
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
from mididivisi.ui.theme import COLORS


def _help_badge(tooltip_text):
    """A small "?" label carrying the fuller explanation as a hover
    tooltip - keeps the dialog itself short and scannable rather than
    reading like documentation, while the detail is still one hover
    away for anyone who wants it.
    """
    badge = QLabel("?")
    badge.setFixedSize(16, 16)
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge.setStyleSheet(
        f"border: 1px solid {COLORS['text_muted']}; border-radius: 8px; "
        f"color: {COLORS['text_muted']}; font-weight: bold; font-size: 10px;"
    )
    badge.setToolTip(tooltip_text)
    return badge


class MidifiDialog(QDialog):
    def __init__(self, current_config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Midi-fy")
        self.setMinimumWidth(340)

        self.original_config = current_config  # kept for the rebuild-vs-instant comparison in _apply()
        self.result_config = None  # set by _apply() if the user confirms
        self.requires_rebuild = False  # set by _apply() - tells the caller which path to take

        layout = QVBoxLayout(self)

        # --- Tremolo section ---
        layout.addWidget(QLabel("<b>Tremolo</b>"))

        threshold_row = QHBoxLayout()
        threshold_row.addWidget(QLabel("Unmeasured threshold (flags):"))

        self.threshold_spin = QSpinBox()
        self.threshold_spin.setRange(1, 8)
        self.threshold_spin.setValue(current_config.tremolo_min_unmeasured_flags)
        self.threshold_spin.setFixedSize(90, 28)
        threshold_row.addWidget(self.threshold_spin)

        threshold_row.addWidget(_help_badge(
            "Tremolo with FEWER flags than this becomes real repeated "
            "notes. At or above, it stays one sustained note for a "
            "tremolo patch. Changing this rebuilds the session."
        ))
        threshold_row.addStretch(1)
        layout.addLayout(threshold_row)

        # --- Trills section ---
        layout.addWidget(QLabel("<b>Trills</b>"))

        trill_rate_row = QHBoxLayout()
        trill_rate_row.addWidget(QLabel("Rate (notes/quarter):"))

        self.trill_rate_spin = QSpinBox()
        self.trill_rate_spin.setRange(2, 32)
        self.trill_rate_spin.setValue(current_config.trill_notes_per_quarter)
        self.trill_rate_spin.setFixedSize(90, 28)
        trill_rate_row.addWidget(self.trill_rate_spin)

        trill_rate_row.addWidget(_help_badge(
            "How fast a toggled-on trill alternates, tempo-relative. "
            "Toggle trills on per-row in the tree; this sets the rate "
            "for all of them. Applies instantly, no rebuild needed."
        ))
        trill_rate_row.addStretch(1)
        layout.addLayout(trill_rate_row)

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
        new_tremolo_threshold = self.threshold_spin.value()
        new_trill_rate = self.trill_rate_spin.value()

        tremolo_changed = (
            new_tremolo_threshold != self.original_config.tremolo_min_unmeasured_flags
        )

        # Only warn/confirm if the REBUILD-requiring setting actually
        # changed - a trill-rate-only change never needs this, and
        # asking anyway would train the user to distrust "Apply" as
        # always-destructive when it usually isn't.
        if tremolo_changed:
            confirmed = QMessageBox.question(
                self,
                "Rebuild session?",
                "Changing the tremolo threshold rebuilds the session from "
                "the original score file - any manual merges, renames, or "
                "other changes made since the file was loaded will be "
                "discarded. (The trill rate change applies instantly and "
                "doesn't need this.) Continue?",
                QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
                QMessageBox.StandardButton.Cancel,
            )
            if confirmed != QMessageBox.StandardButton.Yes:
                return

        new_config = MidifiConfig()
        new_config.tremolo_min_unmeasured_flags = new_tremolo_threshold
        new_config.trill_notes_per_quarter = new_trill_rate

        self.result_config = new_config
        self.requires_rebuild = tremolo_changed
        self.accept()
