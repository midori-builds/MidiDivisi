"""
MidiDivisi main window.

Three areas, per the current UI design:
  1. Toolbar (top) - Open/Import, Export, Merge, Auto Merge, Rename.
     Export opens a dialog (ExportDialog) that owns both export modes
     (Export All / Export Per Instrument), the destination folder,
     the filename, and a dedicated inclusion tree.
  2. Track view (main area) - a QTreeWidget. Top-level items are
     Instruments; children are their current articulation Groups.
     Checkboxes on any row are a pure SELECTION mechanism (for
     merge/rename targeting) - NOT an export-inclusion control (that
     lives in ExportDialog's own tree, bound to Group.included /
     Instrument.included instead). A small "M" in the second column
     marks a merged row; double-clicking it splits the merge back
     apart. Double-clicking a row's name cell renames it in place.
  3. Status bar (bottom) - short transient messages (loaded, merged,
     split). Export feedback and failures use modal dialogs (handled
     inside ExportDialog itself), so they can't be missed.
"""

import os

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QMainWindow,
    QTreeWidget,
    QTreeWidgetItem,
    QFileDialog,
    QMessageBox,
)

from mididivisi.core.parser import load_score
from mididivisi.core.session import Session
from mididivisi.ui.export_dialog import ExportDialog
from mididivisi.ui.settings_dialog import SettingsDialog

# Tree column indices
COL_NAME = 0
COL_MERGED = 1

# Explicit fixed row height - see the matching comment in
# export_dialog.py for why this is needed (Qt/QSS row-height drift on
# repeated collapse/expand) and why width must be 0, not -1.
ROW_HEIGHT = 26


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MidiDivisi")
        self.resize(900, 650)

        # Holds the current Session (Track/Group/Instrument data) and
        # the source file path (used to default the export folder and
        # filename). Both are None until a file is loaded successfully.
        self.session = None
        self.loaded_file_path = None

        # Chronological list of currently-checked QTreeWidgetItems -
        # tracked explicitly (not derived by re-scanning the tree)
        # because "first checked" determines the resulting name on
        # merge, and that's about click ORDER, not tree position.
        self.check_order = []

        self._build_toolbar()
        self._build_tree()
        self.statusBar()  # instantiates the status bar

    def _build_toolbar(self):
        toolbar = self.addToolBar("Main")
        toolbar.setMovable(False)

        self.open_action = QAction("Import", self)
        self.open_action.triggered.connect(self.load_musicxml)
        toolbar.addAction(self.open_action)

        toolbar.addSeparator()

        self.export_action = QAction("Export", self)
        self.export_action.triggered.connect(self.open_export_dialog)
        self.export_action.setEnabled(False)
        toolbar.addAction(self.export_action)

        toolbar.addSeparator()

        self.merge_action = QAction("Merge", self)
        self.merge_action.triggered.connect(self.merge_selected)
        self.merge_action.setEnabled(False)
        toolbar.addAction(self.merge_action)

        self.auto_merge_action = QAction("Auto Merge", self)
        self.auto_merge_action.triggered.connect(self.auto_merge)
        self.auto_merge_action.setEnabled(False)
        toolbar.addAction(self.auto_merge_action)

        self.rename_action = QAction("Rename", self)
        self.rename_action.triggered.connect(self.rename_selected)
        self.rename_action.setEnabled(False)
        toolbar.addAction(self.rename_action)

        toolbar.addSeparator()

        self.settings_action = QAction("Settings", self)
        self.settings_action.triggered.connect(self.open_settings_dialog)
        toolbar.addAction(self.settings_action)  # always enabled - not tied to a loaded score

    def _build_tree(self):
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Track", "Merged"])
        self.tree.setColumnWidth(COL_NAME, 500)
        # Checkboxes are the selection mechanism here, not native row
        # highlighting - disable native selection so the two don't
        # visually compete with each other.
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.NoSelection)
        self.tree.itemChanged.connect(self.on_item_changed)
        self.tree.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.setCentralWidget(self.tree)

    # --- Tree population -------------------------------------------------

    def refresh_tree(self):
        """Rebuild the tree from the current session state. Called
        after load, merge, and split - anything that changes which
        Instruments/Groups exist or how they're named.
        """
        self.tree.blockSignals(True)  # avoid itemChanged firing while rebuilding
        self.tree.clear()
        self.check_order = []

        for instrument in self.session.instruments:
            instrument_item = QTreeWidgetItem(self.tree)
            instrument_item.setFlags(
                instrument_item.flags()
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsEditable
            )
            instrument_item.setCheckState(COL_NAME, Qt.CheckState.Unchecked)
            instrument_item.setText(COL_NAME, instrument.name)
            instrument_item.setData(COL_NAME, Qt.ItemDataRole.UserRole, ("instrument", instrument))
            instrument_item.setSizeHint(COL_NAME, QSize(0, ROW_HEIGHT))

            if instrument.is_merged:
                instrument_item.setText(COL_MERGED, "M")
                tooltip = "Merged from: " + ", ".join(
                    i.name for i in instrument.identities
                )
                instrument_item.setToolTip(COL_MERGED, tooltip)

            for group in instrument.groups:
                group_item = QTreeWidgetItem(instrument_item)
                group_item.setFlags(
                    group_item.flags()
                    | Qt.ItemFlag.ItemIsUserCheckable
                    | Qt.ItemFlag.ItemIsEditable
                )
                group_item.setCheckState(COL_NAME, Qt.CheckState.Unchecked)
                group_item.setText(COL_NAME, group.name)
                group_item.setData(COL_NAME, Qt.ItemDataRole.UserRole, ("group", group))
                group_item.setSizeHint(COL_NAME, QSize(0, ROW_HEIGHT))

                if group.is_merged:
                    group_item.setText(COL_MERGED, "M")
                    tooltip = "Merged from: " + ", ".join(
                        t.name for t in group.tracks
                    )
                    group_item.setToolTip(COL_MERGED, tooltip)

        self.tree.expandAll()
        self.tree.blockSignals(False)
        self.update_action_states()

    # --- Selection (checkbox) bookkeeping ---------------------------------

    def get_checked_items(self):
        """Return (checked_instrument_items, checked_group_items), each
        in the chronological order they were checked (not tree order).
        """
        instruments = []
        groups = []
        for item in self.check_order:
            data_type, _obj = item.data(COL_NAME, Qt.ItemDataRole.UserRole)
            if data_type == "instrument":
                instruments.append(item)
            else:
                groups.append(item)
        return instruments, groups

    def update_action_states(self):
        """Recompute Merge/Rename enabled state from current
        selection. Merge is only valid for 2+ instruments, or 2+
        groups that all share the same parent instrument - never a
        mix of the two levels, and never groups spanning instruments.
        """
        checked_instruments, checked_groups = self.get_checked_items()

        can_merge = False
        if checked_instruments and not checked_groups:
            can_merge = len(checked_instruments) >= 2
        elif checked_groups and not checked_instruments:
            # QTreeWidgetItem isn't hashable, so compare parent
            # identity via id() rather than putting items in a set.
            parent_ids = {id(g.parent()) for g in checked_groups}
            can_merge = len(checked_groups) >= 2 and len(parent_ids) == 1

        self.merge_action.setEnabled(can_merge)

        total_checked = len(checked_instruments) + len(checked_groups)
        self.rename_action.setEnabled(total_checked == 1)

    def on_item_changed(self, item, column):
        if column != COL_NAME:
            return

        data_type, obj = item.data(COL_NAME, Qt.ItemDataRole.UserRole)

        # Detect a text/name edit (vs a checkbox toggle) by comparing
        # against the underlying session object's current name - both
        # land in this same signal.
        new_text = item.text(COL_NAME)
        if new_text != obj.name and new_text.strip():
            obj.rename(new_text)
            self.statusBar().showMessage(f"Renamed to: {new_text}", 4000)

        if item.checkState(COL_NAME) == Qt.CheckState.Checked:
            if item not in self.check_order:
                self.check_order.append(item)
        else:
            if item in self.check_order:
                self.check_order.remove(item)

        self.update_action_states()

    def on_item_double_clicked(self, item, column):
        # Double-clicking the "M" column splits a merged row back
        # apart. Double-clicking the name column is handled natively
        # by Qt's inline editor (ItemIsEditable) - nothing to do here
        # for that case.
        if column != COL_MERGED:
            return

        data_type, obj = item.data(COL_NAME, Qt.ItemDataRole.UserRole)
        if not obj.is_merged:
            return

        if data_type == "instrument":
            self.session.split_instrument(obj.id)
            self.statusBar().showMessage(f"Split instrument: {obj.name}", 4000)
        else:
            self.session.split_group(obj.id)
            self.statusBar().showMessage(f"Split articulation: {obj.name}", 4000)

        self.refresh_tree()

    # --- Toolbar actions ---------------------------------------------------

    def load_musicxml(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open / Import MusicXML",
            "",
            "MusicXML Files (*.xml *.musicxml *.mxl);;All Files (*)",
        )

        if not file_path:
            return  # user cancelled the dialog

        try:
            score = load_score(file_path)
        except Exception as e:
            QMessageBox.critical(self, "Failed to load file", str(e))
            return

        self.session = Session.from_score(score)
        self.loaded_file_path = file_path

        self.export_action.setEnabled(True)
        self.auto_merge_action.setEnabled(True)

        self.refresh_tree()
        self.statusBar().showMessage(
            f"Loaded: {os.path.basename(file_path)} "
            f"({len(self.session.instruments)} instrument(s), "
            f"{len(self.session.tracks)} track(s))",
            6000,
        )

    def merge_selected(self):
        checked_instruments, checked_groups = self.get_checked_items()

        try:
            if checked_instruments:
                ids = [
                    item.data(COL_NAME, Qt.ItemDataRole.UserRole)[1].id
                    for item in checked_instruments
                ]
                self.session.merge_instruments(ids)
                self.statusBar().showMessage(
                    f"Merged {len(ids)} instrument(s)", 4000
                )
            elif checked_groups:
                ids = [
                    item.data(COL_NAME, Qt.ItemDataRole.UserRole)[1].id
                    for item in checked_groups
                ]
                self.session.merge_groups(ids)
                self.statusBar().showMessage(
                    f"Merged {len(ids)} articulation(s)", 4000
                )
            else:
                return
        except ValueError as e:
            QMessageBox.critical(self, "Merge failed", str(e))
            return

        self.refresh_tree()

    def auto_merge(self):
        """First-pass heuristic: merge any current instruments that
        share the same ORIGINAL part name (not display name, which is
        mutable). Duplicate original names is exactly the signal for
        grand-staff/divisi-reserved-staff duplicates (e.g. Harp, or a
        Violin I divisi staff) that this whole Instrument tier was
        built to eventually resolve. No confirmation step yet - runs
        immediately when clicked.
        """
        if self.session is None:
            return

        buckets = {}
        for instrument in self.session.instruments:
            key = tuple(sorted(ident.original_name for ident in instrument.identities))
            buckets.setdefault(key, []).append(instrument)

        merged_count = 0
        for key, instruments in buckets.items():
            if len(instruments) >= 2:
                self.session.merge_instruments([i.id for i in instruments])
                merged_count += 1

        if merged_count:
            self.statusBar().showMessage(
                f"Auto-merged {merged_count} group(s) of matching instruments", 5000
            )
        else:
            self.statusBar().showMessage("Auto merge: no matching instruments found", 4000)

        self.refresh_tree()

    def rename_selected(self):
        checked_instruments, checked_groups = self.get_checked_items()
        all_checked = checked_instruments + checked_groups
        if len(all_checked) != 1:
            return
        self.tree.editItem(all_checked[0], COL_NAME)

    def open_export_dialog(self):
        if self.session is None:
            return

        default_folder = ""
        default_filename = "export.mid"
        if self.loaded_file_path:
            default_folder = os.path.dirname(self.loaded_file_path)
            base = os.path.splitext(os.path.basename(self.loaded_file_path))[0]
            default_filename = f"{base}.mid"

        dialog = ExportDialog(self.session, default_folder, default_filename, parent=self)
        dialog.exec()
        # Inclusion state lives on the actual Group/Instrument objects,
        # so it persists automatically whether or not an export ran -
        # nothing to sync back here.

    def open_settings_dialog(self):
        # Not tied to a loaded score - Settings edits keyword mapping
        # (and future categories) globally, independent of any
        # currently-open file. Changes apply live/immediately (see
        # KeywordMappingPage) and take effect on the NEXT file load,
        # not retroactively on an already-loaded session.
        dialog = SettingsDialog(parent=self)
        dialog.exec()

