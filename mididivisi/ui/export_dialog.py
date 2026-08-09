"""
Export dialog.

One entry point for both export modes (Export All / Export Per
Instrument), plus the destination folder, filename (for Export All),
and a dedicated inclusion tree - completely separate from the main
window's tree, since checkboxes there mean "selected for merge",
while checkboxes here mean "included in export" (Group.included /
Instrument.included).

Unchecking an instrument disables (greys out) its articulation rows
without touching their individual included state - so re-checking the
instrument restores whatever each articulation was set to before,
rather than resetting everything to included.
"""

import os

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QFileDialog,
    QMessageBox,
)

from mididivisi.core.exporter import (
    export_session_to_midi,
    export_session_to_midi_per_instrument,
)

COL_NAME = 0

# Explicit fixed row height. Without this, Qt recomputes each item's
# height from the QSS padding (QTreeWidget::item in theme.py) on every
# collapse/expand cycle, and that recomputation can drift upward
# instead of staying stable - the "rows get taller every time you
# reopen a group" bug. Fixing the height via setSizeHint sidesteps the
# recomputation entirely rather than fighting it. Width must be a
# non-negative value (0 works fine) - QSize(-1, height) is silently
# discarded by PyQt6 rather than being treated as "auto width";
# verified directly, not documented behavior. Actual column width is
# still controlled separately (by the column-width/header setting),
# so a width of 0 here only affects height.
ROW_HEIGHT = 26


class ExportDialog(QDialog):
    def __init__(self, session, default_folder, default_filename, parent=None):
        super().__init__(parent)
        self.session = session
        self.setWindowTitle("Export")
        self.resize(600, 550)

        layout = QVBoxLayout(self)

        # --- Folder row ---
        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("Save to folder:"))
        self.folder_edit = QLineEdit(default_folder)
        folder_row.addWidget(self.folder_edit, 1)
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self.browse_folder)
        folder_row.addWidget(browse_button)
        layout.addLayout(folder_row)

        # --- Filename row (Export All only) ---
        filename_row = QHBoxLayout()
        filename_row.addWidget(QLabel("File name (Export All):"))
        self.filename_edit = QLineEdit(default_filename)
        filename_row.addWidget(self.filename_edit, 1)
        layout.addLayout(filename_row)

        # --- Inclusion tree ---
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Include"])
        self.tree.itemChanged.connect(self.on_item_changed)
        layout.addWidget(self.tree, 1)
        self.populate_tree()

        # --- Action buttons ---
        button_row = QHBoxLayout()
        export_all_button = QPushButton("Export All")
        export_all_button.clicked.connect(self.do_export_all)
        button_row.addWidget(export_all_button)

        export_per_instrument_button = QPushButton("Export Per Instrument")
        export_per_instrument_button.clicked.connect(self.do_export_per_instrument)
        button_row.addWidget(export_per_instrument_button)

        button_row.addStretch(1)
        cancel_button = QPushButton("Close")
        cancel_button.clicked.connect(self.reject)
        button_row.addWidget(cancel_button)

        layout.addLayout(button_row)

    # --- Tree population -------------------------------------------------

    def populate_tree(self):
        self.tree.blockSignals(True)
        self.tree.clear()

        for instrument in self.session.instruments:
            instrument_item = QTreeWidgetItem(self.tree)
            instrument_item.setFlags(
                instrument_item.flags() | Qt.ItemFlag.ItemIsUserCheckable
            )
            instrument_item.setCheckState(
                COL_NAME,
                Qt.CheckState.Checked if instrument.included else Qt.CheckState.Unchecked,
            )
            instrument_item.setText(COL_NAME, instrument.name)
            instrument_item.setData(COL_NAME, Qt.ItemDataRole.UserRole, ("instrument", instrument))
            instrument_item.setSizeHint(COL_NAME, QSize(0, ROW_HEIGHT))

            for group in instrument.groups:
                group_item = QTreeWidgetItem(instrument_item)
                group_item.setFlags(
                    group_item.flags() | Qt.ItemFlag.ItemIsUserCheckable
                )
                group_item.setCheckState(
                    COL_NAME,
                    Qt.CheckState.Checked if group.included else Qt.CheckState.Unchecked,
                )
                group_item.setText(COL_NAME, group.name)
                group_item.setData(COL_NAME, Qt.ItemDataRole.UserRole, ("group", group))
                group_item.setDisabled(not instrument.included)
                group_item.setSizeHint(COL_NAME, QSize(0, ROW_HEIGHT))

        self.tree.expandAll()
        self.tree.blockSignals(False)

    def on_item_changed(self, item, column):
        if column != COL_NAME:
            return

        data_type, obj = item.data(COL_NAME, Qt.ItemDataRole.UserRole)
        is_checked = item.checkState(COL_NAME) == Qt.CheckState.Checked
        obj.included = is_checked

        if data_type == "instrument":
            # Disable (grey out) children without touching their own
            # checked state/included value - it's preserved for when
            # the instrument is re-checked.
            for i in range(item.childCount()):
                item.child(i).setDisabled(not is_checked)

    # --- Folder browsing ---------------------------------------------------

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Choose a folder", self.folder_edit.text()
        )
        if folder:
            self.folder_edit.setText(folder)

    # --- Export actions ---------------------------------------------------

    def do_export_all(self):
        folder = self.folder_edit.text().strip()
        filename = self.filename_edit.text().strip()

        if not folder or not os.path.isdir(folder):
            QMessageBox.critical(self, "Export failed", "Please choose a valid folder.")
            return
        if not filename:
            QMessageBox.critical(self, "Export failed", "Please enter a file name.")
            return
        if not filename.lower().endswith(".mid"):
            filename += ".mid"

        output_path = os.path.join(folder, filename)

        try:
            export_session_to_midi(self.session, output_path)
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))
            return

        QMessageBox.information(self, "Export complete", f"Exported MIDI to:\n{output_path}")
        self.accept()

    def do_export_per_instrument(self):
        folder = self.folder_edit.text().strip()

        if not folder or not os.path.isdir(folder):
            QMessageBox.critical(self, "Export failed", "Please choose a valid folder.")
            return

        try:
            written_paths = export_session_to_midi_per_instrument(self.session, folder)
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))
            return

        QMessageBox.information(
            self,
            "Export complete",
            f"Exported {len(written_paths)} MIDI file(s) to:\n{folder}",
        )
        self.accept()
