"""
Midi-fy tool dialog.

Deliberately a STANDALONE tool, not a Settings page - the right
tremolo threshold and trill rate genuinely depend on the piece (a
3-flag tremolo means something different in a slow piece than a fast
one; trill rate is tempo-relative), so this is per-song configuration,
not a global default (see design discussion in BACKLOG.md's Note-
transformation features section).

Applying a change here does NOT uniformly do the same thing for every
setting - this is a real, deliberate split, not an inconsistency:
- Tremolo's threshold change still triggers a FULL SESSION REBUILD
  (re-parse the original file with the new config), because tremolo
  realization is a destructive, parse-time rewrite - there is nothing
  in memory to recompute FROM otherwise. Consistent with how this app
  already handles Profile reapplication ("always rebuild clean from
  source"). This discards any manual merges/renames/etc. made since
  the file was loaded, so it's confirmed before happening.
- Trill rate changes apply INSTANTLY, no rebuild, no warning - trill
  realization is computed fresh on demand every time (see
  Track.get_active_notes / core/midifi.py), so a rate change just
  means the NEXT redraw/export naturally reflects it. Forcing a
  rebuild here would defeat the entire point of building that
  non-destructive architecture in the first place.

_apply() below compares old vs. new values to decide which path
applies, rather than the caller having to know the difference itself.
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
        self.resize(480, 320)

        self.original_config = current_config  # kept for the rebuild-vs-instant comparison in _apply()
        self.result_config = None  # set by _apply() if the user confirms
        self.requires_rebuild = False  # set by _apply() - tells the caller which path to take

        layout = QVBoxLayout(self)

        # --- Tremolo section ---
        layout.addWidget(QLabel("<b>Tremolo</b>"))

        tremolo_intro = QLabel(
            "A single-note tremolo with FEWER flags than this threshold gets "
            "realized into literal repeated notes (e.g. 1 flag \u2192 2 notes, "
            "2 flags \u2192 4 notes). At or above this threshold, it stays a "
            "single sustained note for a dedicated tremolo patch. Changing "
            "this rebuilds the session from the original file."
        )
        tremolo_intro.setWordWrap(True)
        layout.addWidget(tremolo_intro)

        threshold_row = QHBoxLayout()
        threshold_row.addWidget(QLabel("Minimum flags for unmeasured tremolo:"))

        self.threshold_spin = QSpinBox()
        self.threshold_spin.setRange(1, 8)
        self.threshold_spin.setValue(current_config.tremolo_min_unmeasured_flags)
        self.threshold_spin.setFixedSize(90, 28)
        threshold_row.addWidget(self.threshold_spin)

        threshold_row.addStretch(1)
        layout.addLayout(threshold_row)

        # --- Trills section ---
        layout.addWidget(QLabel("<b>Trills</b>"))

        trill_intro = QLabel(
            "Rate for a realized trill's alternation, in notes per quarter "
            "note (tempo-relative, not a fixed speed - stays musically "
            "correct across tempo changes). Toggle individual trills on in "
            "the tree; this controls the rate for all of them. Changing "
            "this applies instantly - no rebuild needed."
        )
        trill_intro.setWordWrap(True)
        layout.addWidget(trill_intro)

        trill_rate_row = QHBoxLayout()
        trill_rate_row.addWidget(QLabel("Trill notes per quarter note:"))

        self.trill_rate_spin = QSpinBox()
        self.trill_rate_spin.setRange(2, 32)
        self.trill_rate_spin.setValue(current_config.trill_notes_per_quarter)
        self.trill_rate_spin.setFixedSize(90, 28)
        trill_rate_row.addWidget(self.trill_rate_spin)

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
