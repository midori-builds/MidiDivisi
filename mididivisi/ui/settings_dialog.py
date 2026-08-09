"""
Settings dialog.

Sidebar list on the left (one entry per settings category), detail
panel on the right (QStackedWidget - one page per category). Only one
page is functional today (Keyword Mapping), but the framework is
built generically so adding more categories later (Dynamics/Velocity
Mapping, Sample Library Profiles, etc. - see BACKLOG.md) means writing
a new page widget and adding one line to _build_pages, not
restructuring anything.
"""

from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QVBoxLayout,
    QGridLayout,
    QListWidget,
    QStackedWidget,
    QWidget,
    QLabel,
    QListWidgetItem,
    QPushButton,
    QLineEdit,
    QInputDialog,
    QScrollArea,
    QFrame,
    QMessageBox,
    QSpinBox,
)

from mididivisi.core.settings import (
    settings,
    KEYWORD_CATEGORY_LABELS,
    DYNAMIC_MARKING_ORDER,
)


class KeywordMappingPage(QWidget):
    """One row per keyword category: a label, a live QListWidget of
    the current words, and Add/Remove/Reset controls. Every change
    (add, remove, reset) is applied to the shared `settings` instance
    and saved to disk immediately - no separate Save button, matching
    how the rest of the app already applies changes (rename, merge,
    checkbox toggles) immediately rather than needing an explicit
    commit step.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)

        reset_all_row = QHBoxLayout()
        reset_all_row.addStretch(1)
        reset_all_button = QPushButton("Reset All to Defaults")
        reset_all_button.clicked.connect(self.reset_all_categories)
        reset_all_row.addWidget(reset_all_button)
        layout.addLayout(reset_all_row)

        self.category_widgets = {}  # category -> QListWidget

        for category, label in KEYWORD_CATEGORY_LABELS.items():
            layout.addWidget(QLabel(f"<b>{label}</b>"))

            row = QHBoxLayout()

            word_list = QListWidget()
            word_list.setFixedHeight(90)
            for word in settings.keyword_mapping.get(category, []):
                word_list.addItem(word)
            self.category_widgets[category] = word_list
            row.addWidget(word_list, 1)

            button_col = QVBoxLayout()

            add_button = QPushButton("Add")
            add_button.clicked.connect(lambda _, c=category: self.add_word(c))
            button_col.addWidget(add_button)

            remove_button = QPushButton("Remove")
            remove_button.clicked.connect(lambda _, c=category: self.remove_selected_word(c))
            button_col.addWidget(remove_button)

            reset_button = QPushButton("Reset")
            reset_button.clicked.connect(lambda _, c=category: self.reset_category(c))
            button_col.addWidget(reset_button)

            button_col.addStretch(1)
            row.addLayout(button_col)

            layout.addLayout(row)

        layout.addStretch(1)

    def add_word(self, category):
        text, ok = QInputDialog.getText(self, "Add word", "Word or phrase:")
        if not ok:
            return
        text = text.strip()
        if not text:
            return

        settings.keyword_mapping.setdefault(category, [])
        if text.lower() not in {w.lower() for w in settings.keyword_mapping[category]}:
            settings.keyword_mapping[category].append(text)
            settings.save()
            self.category_widgets[category].addItem(text)

    def remove_selected_word(self, category):
        word_list = self.category_widgets[category]
        selected = word_list.currentItem()
        if selected is None:
            return

        word = selected.text()
        settings.keyword_mapping[category] = [
            w for w in settings.keyword_mapping.get(category, []) if w != word
        ]
        settings.save()
        word_list.takeItem(word_list.row(selected))

    def reset_category(self, category):
        settings.reset_category_to_default(category)
        settings.save()

        word_list = self.category_widgets[category]
        word_list.clear()
        for word in settings.keyword_mapping.get(category, []):
            word_list.addItem(word)

    def reset_all_categories(self):
        # Only THIS button asks for confirmation, deliberately - the
        # per-category Reset buttons stay one-click/no-confirmation on
        # purpose (low blast radius, meant to be a frictionless safety
        # net). This one can wipe custom words across every category
        # at once, which is a meaningfully bigger loss to risk on a
        # misclick.
        confirmed = QMessageBox.question(
            self,
            "Reset all keyword mappings?",
            "This will remove any custom words you've added across "
            "every category and restore the built-in defaults.",
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.Cancel,
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return

        # Reuses reset_category per category rather than duplicating
        # its logic - saves once at the end instead of once per
        # category, since settings.save() is a full-file write and
        # there's no need to hit disk 12 times for one user action.
        for category in self.category_widgets:
            settings.reset_category_to_default(category)

            word_list = self.category_widgets[category]
            word_list.clear()
            for word in settings.keyword_mapping.get(category, []):
                word_list.addItem(word)

        settings.save()


class DynamicsMappingPage(QWidget):
    """One row per dynamic marking (ppp through fff): a label and a
    QSpinBox for its velocity (0-127). Unlike Keyword Mapping, each
    marking has exactly one value rather than a list of words, so
    there's no Add/Remove - just direct editing, saved immediately on
    every change (same immediate-commit philosophy as Keyword
    Mapping's per-word edits).
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)

        reset_all_row = QHBoxLayout()
        reset_all_row.addStretch(1)
        reset_all_button = QPushButton("Reset All to Defaults")
        reset_all_button.clicked.connect(self.reset_all)
        reset_all_row.addWidget(reset_all_button)
        layout.addLayout(reset_all_row)

        grid = QGridLayout()
        self.spin_boxes = {}  # marking -> QSpinBox

        for row, marking in enumerate(DYNAMIC_MARKING_ORDER):
            grid.addWidget(QLabel(marking), row, 0)

            spin_box = QSpinBox()
            spin_box.setRange(0, 127)
            spin_box.setValue(settings.dynamics_mapping.get(marking, 0))
            spin_box.setFixedSize(90, 28)  # explicit size - don't rely on native
                                            # sizing/CSS max-height alone, which
                                            # rendered oddly oversized in testing
            spin_box.valueChanged.connect(
                lambda value, m=marking: self.set_velocity(m, value)
            )
            self.spin_boxes[marking] = spin_box
            grid.addWidget(spin_box, row, 1)
            grid.setColumnStretch(2, 1)  # push the fixed-size spin boxes to the left instead of stretching them

        layout.addLayout(grid)
        layout.addStretch(1)

    def set_velocity(self, marking, value):
        settings.dynamics_mapping[marking] = value
        settings.save()

    def reset_all(self):
        confirmed = QMessageBox.question(
            self,
            "Reset all dynamics mappings?",
            "This will restore the built-in velocity values for every "
            "dynamic marking.",
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.Cancel,
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return

        settings.reset_dynamics_to_default()
        settings.save()

        for marking, spin_box in self.spin_boxes.items():
            # blockSignals so setting the value doesn't fire
            # valueChanged -> set_velocity -> another redundant save()
            # for each of the 8 spin boxes.
            spin_box.blockSignals(True)
            spin_box.setValue(settings.dynamics_mapping.get(marking, 0))
            spin_box.blockSignals(False)


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(760, 650)
        self.setMinimumSize(600, 450)

        layout = QVBoxLayout(self)

        top_row = QHBoxLayout()

        self.category_list = QListWidget()
        self.category_list.setFixedWidth(180)
        top_row.addWidget(self.category_list)

        self.pages = QStackedWidget()
        top_row.addWidget(self.pages, 1)

        layout.addLayout(top_row, 1)

        # Bottom bar - deliberately OUTSIDE the scrollable page area, so
        # Close is always visible and reachable regardless of scroll
        # position, per how the dialog is meant to behave.
        bottom_row = QHBoxLayout()
        bottom_row.addStretch(1)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        bottom_row.addWidget(close_button)
        layout.addLayout(bottom_row)

        self._build_pages()

        self.category_list.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.category_list.setCurrentRow(0)

    def _build_pages(self):
        self._add_page("Keyword Mapping", KeywordMappingPage())
        self._add_page("Dynamics Mapping", DynamicsMappingPage())
        # Future pages (Sample Library Profiles, etc.) get added here
        # the same way - see BACKLOG.md for what's planned.

    def _add_page(self, label, widget):
        """Every page gets wrapped in a scroll area automatically, so
        a future page with a lot of content doesn't need to handle
        scrolling itself - it just needed to be added once, generally,
        here, rather than per-page. Keyword Mapping is what surfaced
        the need for this: 6 categories x (label + list + 3 buttons)
        overflows a fixed-height dialog with no scroll wrapper.
        """
        QListWidgetItem(label, self.category_list)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)  # avoid a double border against the dialog's own edge
        scroll.setWidget(widget)

        self.pages.addWidget(scroll)
