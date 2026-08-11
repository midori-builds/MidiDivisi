"""
Profile picker dialog.

Lightweight, selection-only - deliberately NOT the Profile Manager
(that's a separate, standalone window for actually building/editing
profiles). Opened per-instrument from the main tree's "Select
Profile" button. Offers a shortcut link to open the Profile Manager
(e.g. if the user realizes mid-pick that they need to create/edit a
profile first), and a way to clear an existing assignment.

Profiles with an empty articulation inventory are shown but disabled
(with a tooltip) rather than hidden - a profile that exists but has
nothing defined in it yet is a real, visible state the user should be
able to see and understand, not one that silently disappears from the
list.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTreeWidget,
    QTreeWidgetItem,
    QPushButton,
    QLabel,
)

from mididivisi.core.profiles import library

TREE_ROLE = Qt.ItemDataRole.UserRole


class ProfilePickerDialog(QDialog):
    def __init__(self, instrument_name, current_profile, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Select Profile - {instrument_name}")
        self.resize(450, 500)

        # Set by the caller after exec() via .selected_profile /
        # .clear_requested - "select", "clear", or neither (cancelled).
        self.selected_profile = None
        self.clear_requested = False
        self.open_manager_requested = False

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Choose a profile for: {instrument_name}"))

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Collections / Profiles"])
        self.tree.itemSelectionChanged.connect(self._update_button_states)
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self.tree, 1)

        button_row = QHBoxLayout()

        manager_button = QPushButton("Open Profile Manager...")
        manager_button.clicked.connect(self._open_manager)
        button_row.addWidget(manager_button)

        button_row.addStretch(1)

        self.clear_button = QPushButton("Clear Assignment")
        self.clear_button.clicked.connect(self._clear_assignment)
        self.clear_button.setEnabled(current_profile is not None)
        button_row.addWidget(self.clear_button)

        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_row.addWidget(cancel_button)

        self.select_button = QPushButton("Select")
        self.select_button.clicked.connect(self._confirm_selection)
        self.select_button.setEnabled(False)
        button_row.addWidget(self.select_button)

        layout.addLayout(button_row)

        # Populated LAST, deliberately - _populate_tree can select an
        # item (to pre-select the current profile), which fires
        # itemSelectionChanged -> _update_button_states, and that
        # needs self.select_button to already exist. Building the
        # buttons first, populating after, avoids that ordering bug
        # rather than working around it with signal-blocking.
        self._populate_tree(current_profile)

    def _populate_tree(self, current_profile):
        for collection in library.collections:
            collection_item = QTreeWidgetItem(self.tree)
            collection_item.setText(0, collection.name)
            collection_item.setFlags(Qt.ItemFlag.ItemIsEnabled)  # not selectable itself

            for profile in collection.profiles:
                profile_item = QTreeWidgetItem(collection_item)
                profile_item.setText(0, profile.name)
                profile_item.setData(0, TREE_ROLE, profile)

                if not profile.inventory:
                    profile_item.setFlags(Qt.ItemFlag.NoItemFlags)
                    profile_item.setToolTip(0, "No articulations added")
                else:
                    profile_item.setFlags(
                        Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                    )

                if current_profile is not None and profile.id == current_profile.id:
                    profile_item.setSelected(True)
                    self.tree.setCurrentItem(profile_item)

        self.tree.expandAll()

    def _update_button_states(self):
        selected = self.tree.selectedItems()
        self.select_button.setEnabled(bool(selected))

    def _on_double_click(self, item, column):
        profile = item.data(0, TREE_ROLE)
        if profile is None:
            return
        # Act directly on the double-clicked item rather than
        # delegating to _confirm_selection() (which reads
        # self.tree.selectedItems()) - real mouse double-clicks do
        # select the item first, so that would likely work too, but
        # depending on that implicit ordering is fragile. Acting on
        # the item passed in here is correct regardless.
        self.selected_profile = profile
        self.accept()

    def _confirm_selection(self):
        selected = self.tree.selectedItems()
        if not selected:
            return
        profile = selected[0].data(0, TREE_ROLE)
        if profile is None:
            return
        self.selected_profile = profile
        self.accept()

    def _clear_assignment(self):
        self.clear_requested = True
        self.accept()

    def _open_manager(self):
        self.open_manager_requested = True
        self.reject()
