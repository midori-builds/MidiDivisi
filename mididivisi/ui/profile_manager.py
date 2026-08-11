"""
Profile Manager.

Standalone, non-modal window - deliberately NOT part of Settings and
NOT what pops up from simply selecting a profile for an instrument
(that's ExportDialog-style picker, a separate lightweight dialog).
This is where Collections/Profiles are actually built and edited, and
where collection/profile-level export/import lives.

Layout: a tree on the left (Collections -> Profiles, mirroring the
main window's track tree visual language), an editor on the right
with three parts side by side/stacked - Articulation Inventory,
Keyword Matching (for whichever inventory item is currently
selected), and a Keyswitch editor (also for the selected item).
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTreeWidget,
    QTreeWidgetItem,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QLabel,
    QLineEdit,
    QComboBox,
    QCheckBox,
    QInputDialog,
    QMessageBox,
    QFileDialog,
    QSplitter,
)

from mididivisi.core.profiles import (
    library,
    Collection,
    Profile,
    InventoryItem,
    export_collection,
    import_collection,
    export_profile,
    import_profile,
    DEFAULT_KEYSWITCH_NOTE,
    all_midi_note_names,
)

# Curated preset labels for the Keyword Matching "Add" combo box. Our
# internal vocabulary is genuinely open-ended (any music21
# articulation class name, plus interval-specific trill/tremolo
# combos like "Trill-M2"), so this can't be exhaustive - it's an
# editable combo, meaning anything not listed can still be typed
# directly. This list covers what we've actually seen this vocabulary
# produce so far.
PRESET_LABELS = [
    "Sustain",
    "Staccato",
    "Staccatissimo",
    "Spiccato",
    "Tenuto",
    "Accent",
    "StrongAccent",
    "Marcato",
    "Tremolo",
    "TremoloSpanner",
    "Trill-M2",
    "Trill-m2",
    "Trill-M3",
    "Trill-m3",
    "Glissando",
    "ArtificialHarmonic",
    "StringHarmonic",
    "Pizzicato",
    "Mute",
    "Flutter",
    "SulPont",
    "SulTasto",
    "ColLegno",
]

TREE_ROLE = Qt.ItemDataRole.UserRole


class ProfileManagerWindow(QMainWindow):
    # Emitted whenever anything is saved here (rename, inventory edit,
    # keyword match, keyswitch change, delete, import...) - the main
    # window listens for this and refreshes its own tree, since
    # editing a profile in this separate window otherwise has no way
    # to tell the main window its displayed state (e.g. whether the KS
    # column should show) has gone stale.
    profiles_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Profile Manager")
        self.resize(1000, 650)

        self.current_profile = None  # the Profile currently shown in the editor
        self.current_item = None  # the InventoryItem currently selected within it

        self._build_ui()
        self._refresh_collection_tree()

    def _save(self):
        """Centralized save - EVERY mutation in this window should go
        through this instead of calling library.save() directly, so
        the profiles_changed signal can never be forgotten at a new
        call site.
        """
        library.save()
        self.profiles_changed.emit()

    # --- UI construction -------------------------------------------------

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer = QHBoxLayout(central)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter)

        # --- Left: Collection/Profile tree ---
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)

        self.collection_tree = QTreeWidget()
        self.collection_tree.setHeaderLabels(["Collections / Profiles"])
        self.collection_tree.itemSelectionChanged.connect(self.on_tree_selection_changed)
        self.collection_tree.itemChanged.connect(self.on_tree_item_renamed)
        left_layout.addWidget(self.collection_tree)

        tree_button_row = QHBoxLayout()
        add_collection_button = QPushButton("Add Collection")
        add_collection_button.clicked.connect(self.add_collection)
        tree_button_row.addWidget(add_collection_button)

        self.add_profile_button = QPushButton("Add Profile")
        self.add_profile_button.clicked.connect(self.add_profile)
        self.add_profile_button.setEnabled(False)
        tree_button_row.addWidget(self.add_profile_button)

        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self.delete_selected)
        self.delete_button.setEnabled(False)
        tree_button_row.addWidget(self.delete_button)

        left_layout.addLayout(tree_button_row)

        export_import_row = QHBoxLayout()
        export_collection_button = QPushButton("Export Collection...")
        export_collection_button.clicked.connect(self.export_selected_collection)
        export_import_row.addWidget(export_collection_button)

        import_collection_button = QPushButton("Import Collection...")
        import_collection_button.clicked.connect(self.import_collection_file)
        export_import_row.addWidget(import_collection_button)
        left_layout.addLayout(export_import_row)

        export_import_row2 = QHBoxLayout()
        export_profile_button = QPushButton("Export Profile...")
        export_profile_button.clicked.connect(self.export_selected_profile)
        export_import_row2.addWidget(export_profile_button)

        import_profile_button = QPushButton("Import Profile...")
        import_profile_button.clicked.connect(self.import_profile_file)
        export_import_row2.addWidget(import_profile_button)
        left_layout.addLayout(export_import_row2)

        splitter.addWidget(left_panel)

        # --- Right: editor (built once, populated/cleared as selection changes) ---
        self.editor_widget = self._build_editor()
        splitter.addWidget(self.editor_widget)

        splitter.setSizes([300, 700])

    def _build_editor(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.profile_name_label = QLabel("No profile selected")
        layout.addWidget(self.profile_name_label)

        panels_row = QHBoxLayout()

        # --- Articulation Inventory panel ---
        inventory_panel = QVBoxLayout()
        inventory_panel.addWidget(QLabel("Articulation Inventory"))

        self.inventory_list = QListWidget()
        self.inventory_list.itemSelectionChanged.connect(self.on_inventory_selection_changed)
        inventory_panel.addWidget(self.inventory_list)

        inventory_button_row = QHBoxLayout()
        add_inventory_button = QPushButton("Add")
        add_inventory_button.clicked.connect(self.add_inventory_item)
        inventory_button_row.addWidget(add_inventory_button)
        remove_inventory_button = QPushButton("Remove")
        remove_inventory_button.clicked.connect(self.remove_inventory_item)
        inventory_button_row.addWidget(remove_inventory_button)
        inventory_panel.addLayout(inventory_button_row)

        panels_row.addLayout(inventory_panel)

        # --- Keyword Matching panel ---
        matching_panel = QVBoxLayout()
        matching_panel.addWidget(QLabel("Keyword Matching"))

        self.matching_list = QListWidget()
        matching_panel.addWidget(self.matching_list)

        self.matching_combo = QComboBox()
        self.matching_combo.setEditable(True)
        self.matching_combo.addItems(PRESET_LABELS)
        matching_panel.addWidget(self.matching_combo)

        matching_button_row = QHBoxLayout()
        add_match_button = QPushButton("Add")
        add_match_button.clicked.connect(self.add_matched_label)
        matching_button_row.addWidget(add_match_button)
        remove_match_button = QPushButton("Remove")
        remove_match_button.clicked.connect(self.remove_matched_label)
        matching_button_row.addWidget(remove_match_button)
        auto_add_button = QPushButton("Auto-Add")
        auto_add_button.clicked.connect(self.auto_add_matches)
        matching_button_row.addWidget(auto_add_button)
        matching_panel.addLayout(matching_button_row)

        panels_row.addLayout(matching_panel)

        layout.addLayout(panels_row)

        # --- Keyswitch editor ---
        # Redesigned: keyswitching is enabled/disabled at the PROFILE
        # level (one checkbox for the whole profile), not per
        # articulation - toggling it on assigns DEFAULT_KEYSWITCH_NOTE
        # to every inventory item at once. The per-item note selector
        # below is only about WHICH note the currently-selected item
        # uses (adjustable after the fact) - it's hidden entirely
        # (not just disabled) when the profile checkbox is off, since
        # showing a note selector for a feature that isn't active is
        # more confusing than showing nothing.
        self.profile_keyswitch_checkbox = QCheckBox("Keyswitch on Profile")
        self.profile_keyswitch_checkbox.toggled.connect(self.on_profile_keyswitch_toggled)
        layout.addWidget(self.profile_keyswitch_checkbox)

        self.keyswitch_note_row = QWidget()
        keyswitch_row = QHBoxLayout(self.keyswitch_note_row)
        keyswitch_row.setContentsMargins(0, 0, 0, 0)
        keyswitch_row.addWidget(QLabel("Note for selected articulation:"))

        # A note-NAME picker, not a raw number spinner - a bare MIDI
        # integer means nothing to a composer at a glance. Populated
        # once with every valid note (0-127) shown as e.g. "C2", MIDI
        # number kept as each entry's item data.
        self.keyswitch_combo = QComboBox()
        for name, note_number in all_midi_note_names():
            self.keyswitch_combo.addItem(name, note_number)
        self.keyswitch_combo.setFixedWidth(90)
        self.keyswitch_combo.currentIndexChanged.connect(self.on_keyswitch_note_changed)
        keyswitch_row.addWidget(self.keyswitch_combo)

        keyswitch_row.addStretch(1)
        layout.addWidget(self.keyswitch_note_row)
        self.keyswitch_note_row.setVisible(False)

        layout.addStretch(1)

        self._set_editor_enabled(False)
        return widget

    def _set_editor_enabled(self, enabled):
        self.inventory_list.setEnabled(enabled)
        self.matching_list.setEnabled(enabled)
        self.matching_combo.setEnabled(enabled)
        self.profile_keyswitch_checkbox.setEnabled(enabled)
        if not enabled:
            self.keyswitch_note_row.setVisible(False)

    # --- Tree population ---------------------------------------------------

    def _refresh_collection_tree(self, select_id=None):
        """Rebuild the tree from the library. Since this destroys and
        recreates every QTreeWidgetItem, any action that calls this
        (add/delete/rename) should pass select_id (a Collection or
        Profile id) to restore selection afterward - otherwise the
        user is left with nothing selected even right after creating
        something, which is a real, noticeable regression, not just a
        cosmetic one.
        """
        self.collection_tree.blockSignals(True)
        self.collection_tree.clear()

        item_to_select = None
        for collection in library.collections:
            collection_item = QTreeWidgetItem(self.collection_tree)
            collection_item.setText(0, collection.name)
            collection_item.setFlags(collection_item.flags() | Qt.ItemFlag.ItemIsEditable)
            collection_item.setData(0, TREE_ROLE, ("collection", collection))
            if select_id == collection.id:
                item_to_select = collection_item

            for profile in collection.profiles:
                profile_item = QTreeWidgetItem(collection_item)
                profile_item.setText(0, profile.name)
                profile_item.setFlags(profile_item.flags() | Qt.ItemFlag.ItemIsEditable)
                profile_item.setData(0, TREE_ROLE, ("profile", profile))
                if select_id == profile.id:
                    item_to_select = profile_item

        self.collection_tree.expandAll()
        self.collection_tree.blockSignals(False)

        if item_to_select is not None:
            self.collection_tree.setCurrentItem(item_to_select)

    def _refresh_inventory_list(self):
        self.inventory_list.blockSignals(True)
        self.inventory_list.clear()
        if self.current_profile:
            for item in self.current_profile.inventory:
                list_item = QListWidgetItem(item.name)
                list_item.setData(TREE_ROLE, item)
                self.inventory_list.addItem(list_item)
        self.inventory_list.blockSignals(False)

    def _refresh_matching_list(self):
        self.matching_list.clear()
        if self.current_item:
            for label in self.current_item.matched_labels:
                self.matching_list.addItem(label)

    def _refresh_keyswitch_editor(self):
        """Two levels: the profile-level checkbox reflects
        self.current_profile.keyswitch_enabled. The per-item note row
        is only shown at all when that's True - hidden entirely
        otherwise, not just disabled - and when shown, reflects the
        currently-selected inventory item's own note.
        """
        self.profile_keyswitch_checkbox.blockSignals(True)
        if self.current_profile:
            self.profile_keyswitch_checkbox.setChecked(self.current_profile.keyswitch_enabled)
        else:
            self.profile_keyswitch_checkbox.setChecked(False)
        self.profile_keyswitch_checkbox.blockSignals(False)

        show_note_row = bool(self.current_profile and self.current_profile.keyswitch_enabled
                              and self.current_item)
        self.keyswitch_note_row.setVisible(show_note_row)

        if show_note_row:
            self.keyswitch_combo.blockSignals(True)
            note = self.current_item.keyswitch_note
            note = note if note is not None else DEFAULT_KEYSWITCH_NOTE
            index = self.keyswitch_combo.findData(note)
            if index >= 0:
                self.keyswitch_combo.setCurrentIndex(index)
            self.keyswitch_combo.blockSignals(False)

    # --- Tree selection / editing ------------------------------------------

    def on_tree_selection_changed(self):
        selected = self.collection_tree.selectedItems()
        if not selected:
            self.add_profile_button.setEnabled(False)
            self.delete_button.setEnabled(False)
            self.current_profile = None
            self._set_editor_enabled(False)
            self.profile_name_label.setText("No profile selected")
            self.inventory_list.clear()
            self.matching_list.clear()
            return

        item = selected[0]
        kind, obj = item.data(0, TREE_ROLE)
        self.delete_button.setEnabled(True)

        if kind == "collection":
            self.add_profile_button.setEnabled(True)
            self.current_profile = None
            self._set_editor_enabled(False)
            self.profile_name_label.setText("No profile selected")
            self.inventory_list.clear()
            self.matching_list.clear()
        else:  # "profile"
            self.add_profile_button.setEnabled(False)
            self.current_profile = obj
            self._set_editor_enabled(True)
            self.profile_name_label.setText(f"Profile: {obj.name}")
            self._refresh_inventory_list()
            self.current_item = None
            self.matching_list.clear()
            self._refresh_keyswitch_editor()

    def on_tree_item_renamed(self, item, column):
        kind, obj = item.data(0, TREE_ROLE)
        new_text = item.text(0)
        if new_text and new_text != obj.name:
            obj.name = new_text
            self._save()
            if kind == "profile" and self.current_profile is obj:
                self.profile_name_label.setText(f"Profile: {obj.name}")

    def add_collection(self):
        text, ok = QInputDialog.getText(self, "Add Collection", "Collection name:")
        if not ok or not text.strip():
            return
        collection = library.add_collection(text.strip())
        self._refresh_collection_tree(select_id=collection.id)

    def add_profile(self):
        selected = self.collection_tree.selectedItems()
        if not selected:
            return
        kind, collection = selected[0].data(0, TREE_ROLE)
        if kind != "collection":
            return

        text, ok = QInputDialog.getText(self, "Add Profile", "Profile name:")
        if not ok or not text.strip():
            return

        new_profile = Profile(text.strip())
        collection.profiles.append(new_profile)
        self._save()
        self._refresh_collection_tree(select_id=new_profile.id)

    def delete_selected(self):
        selected = self.collection_tree.selectedItems()
        if not selected:
            return
        kind, obj = selected[0].data(0, TREE_ROLE)

        confirmed = QMessageBox.question(
            self,
            "Delete?",
            f"Delete {kind} '{obj.name}'? This cannot be undone.",
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.Cancel,
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return

        if kind == "collection":
            library.remove_collection(obj.id)
        else:
            parent_collection, _ = library.find_profile(obj.id)
            if parent_collection:
                parent_collection.profiles = [
                    p for p in parent_collection.profiles if p.id != obj.id
                ]
                self._save()

        self._refresh_collection_tree()
        self.on_tree_selection_changed()

    # --- Articulation inventory ---------------------------------------------

    def add_inventory_item(self):
        if not self.current_profile:
            return
        text, ok = QInputDialog.getText(self, "Add Articulation", "Bucket name (e.g. \"Short\"):")
        if not ok or not text.strip():
            return
        self.current_profile.inventory.append(InventoryItem(text.strip()))
        self._save()
        self._refresh_inventory_list()

    def remove_inventory_item(self):
        if not self.current_profile:
            return
        selected = self.inventory_list.selectedItems()
        if not selected:
            return
        item = selected[0].data(TREE_ROLE)
        self.current_profile.inventory = [
            i for i in self.current_profile.inventory if i.id != item.id
        ]
        self._save()
        self._refresh_inventory_list()
        self.current_item = None
        self.matching_list.clear()
        self._refresh_keyswitch_editor()

    def on_inventory_selection_changed(self):
        selected = self.inventory_list.selectedItems()
        if not selected:
            self.current_item = None
        else:
            self.current_item = selected[0].data(TREE_ROLE)
        self._refresh_matching_list()
        self._refresh_keyswitch_editor()

    # --- Keyword matching ---------------------------------------------------

    def add_matched_label(self):
        if not self.current_item or not self.current_profile:
            return
        label = self.matching_combo.currentText().strip()
        if not label:
            return

        # Enforce uniqueness: a label maps to at most one inventory
        # item within a profile - remove it from wherever it
        # currently is (if anywhere) before adding it here, rather
        # than letting apply_profile's label->item lookup silently
        # resolve conflicts by last-write-wins.
        for other_item in self.current_profile.inventory:
            if label in other_item.matched_labels:
                other_item.matched_labels.remove(label)

        if label not in self.current_item.matched_labels:
            self.current_item.matched_labels.append(label)

        self._save()
        self._refresh_matching_list()

    def remove_matched_label(self):
        if not self.current_item:
            return
        selected = self.matching_list.selectedItems()
        if not selected:
            return
        label = selected[0].text()
        if label in self.current_item.matched_labels:
            self.current_item.matched_labels.remove(label)
        self._save()
        self._refresh_matching_list()

    def auto_add_matches(self):
        """Try to match the inventory item's own name against our
        known preset label vocabulary (case-insensitive, exact or
        substring match either direction). A real text-matching
        heuristic, not magic - works well when the item is literally
        named after a technique (e.g. "Staccato"), less useful for
        library-specific bucket names like "Short" that don't
        resemble our internal vocabulary at all.
        """
        if not self.current_item or not self.current_profile:
            return

        name_lower = self.current_item.name.strip().lower()
        if not name_lower:
            return

        matches = [
            label for label in PRESET_LABELS
            if name_lower == label.lower()
            or name_lower in label.lower()
            or label.lower() in name_lower
        ]

        for label in matches:
            for other_item in self.current_profile.inventory:
                if label in other_item.matched_labels:
                    other_item.matched_labels.remove(label)
            if label not in self.current_item.matched_labels:
                self.current_item.matched_labels.append(label)

        self._save()
        self._refresh_matching_list()

        if not matches:
            self.statusBar().showMessage(
                f"Auto-Add: no matches found for \"{self.current_item.name}\"", 4000
            )

    # --- Keyswitch -----------------------------------------------------------

    def on_profile_keyswitch_toggled(self, checked):
        if not self.current_profile:
            return

        self.current_profile.keyswitch_enabled = checked

        if checked:
            # Assign the same default note to EVERY inventory item at
            # once - not incrementing per item yet (auto-keyswitch,
            # planned but not built). Individual notes can still be
            # adjusted afterward via the per-item selector.
            for item in self.current_profile.inventory:
                item.keyswitch_note = DEFAULT_KEYSWITCH_NOTE

        self._save()
        self._refresh_keyswitch_editor()

    def on_keyswitch_note_changed(self, index):
        if not self.current_item or not self.current_profile or not self.current_profile.keyswitch_enabled:
            return
        note_number = self.keyswitch_combo.itemData(index)
        if note_number is None:
            return
        self.current_item.keyswitch_note = note_number
        self._save()

    # --- Export / Import -----------------------------------------------------

    def export_selected_collection(self):
        selected = self.collection_tree.selectedItems()
        if not selected:
            QMessageBox.information(self, "Export Collection", "Select a collection first.")
            return
        kind, obj = selected[0].data(0, TREE_ROLE)
        collection = obj if kind == "collection" else library.find_profile(obj.id)[0]
        if collection is None:
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Export Collection", f"{collection.name}.json", "JSON Files (*.json)"
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        export_collection(collection, path)

    def import_collection_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Collection", "", "JSON Files (*.json);;All Files (*)"
        )
        if not path:
            return
        try:
            collection = import_collection(path)
        except Exception as e:
            QMessageBox.critical(self, "Import failed", str(e))
            return
        library.collections.append(collection)
        self._save()
        self._refresh_collection_tree(select_id=collection.id)

    def export_selected_profile(self):
        if not self.current_profile:
            QMessageBox.information(self, "Export Profile", "Select a profile first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Profile", f"{self.current_profile.name}.json", "JSON Files (*.json)"
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        export_profile(self.current_profile, path)

    def import_profile_file(self):
        selected = self.collection_tree.selectedItems()
        target_collection = None
        if selected:
            kind, obj = selected[0].data(0, TREE_ROLE)
            target_collection = obj if kind == "collection" else library.find_profile(obj.id)[0]

        if target_collection is None:
            QMessageBox.information(
                self, "Import Profile", "Select a collection to import the profile into first."
            )
            return

        path, _ = QFileDialog.getOpenFileName(
            self, "Import Profile", "", "JSON Files (*.json);;All Files (*)"
        )
        if not path:
            return
        try:
            profile = import_profile(path)
        except Exception as e:
            QMessageBox.critical(self, "Import failed", str(e))
            return

        target_collection.profiles.append(profile)
        self._save()
        self._refresh_collection_tree(select_id=profile.id)
