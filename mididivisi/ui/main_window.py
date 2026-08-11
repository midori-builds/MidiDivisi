"""
MidiDivisi main window.

Three areas, per the current UI design:
  1. Menu bar (top) - File menu: Import, Open Session, Save Session,
     Save Session As, a separator, Export, a separator, Settings.
     Toolbar (below the menu bar) keeps only the track-editing
     actions used constantly while actively shaping the track list:
     Merge, Auto Merge, Merge Accents, Rename. This split happened
     once the toolbar grew past ~7 items and stopped being scannable
     - menu bar for organization/completeness, toolbar for one-click
     access to the small set of things reached for constantly.
  2. Track view (main area) - a QTreeWidget. Top-level items are
     Instruments; children are their current articulation Groups.
     Checkboxes on any row are a pure SELECTION mechanism (for
     merge/rename targeting) - NOT an export-inclusion control (that
     lives in ExportDialog's own tree, bound to Group.included /
     Instrument.included instead). A small "M" in the second column
     marks a merged row; double-clicking it splits the merge back
     apart. Double-clicking a row's name cell renames it in place.
  3. Status bar (bottom) - short transient messages (loaded, merged,
     split, session saved/loaded). Export feedback and failures use
     modal dialogs (handled inside ExportDialog itself, or directly
     here for session load/save), so they can't be missed.
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
    QWidget,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QCheckBox,
)

from mididivisi.core.parser import load_score
from mididivisi.core.session import Session
from mididivisi.core import session_file
from mididivisi.ui.export_dialog import ExportDialog
from mididivisi.ui.settings_dialog import SettingsDialog
from mididivisi.ui.profile_manager import ProfileManagerWindow
from mididivisi.ui.profile_picker_dialog import ProfilePickerDialog
from mididivisi.core.profiles import midi_note_name

# Tree column indices
COL_NAME = 0
COL_MERGED = 1
COL_PROFILE = 2
COL_KS = 3

# Explicit fixed row height - see the matching comment in
# export_dialog.py for why this is needed (Qt/QSS row-height drift on
# repeated collapse/expand) and why width must be 0, not -1.
ROW_HEIGHT = 32

# Instrument rows carry an embedded button + checkbox and need more
# vertical breathing room than plain-text group rows - using one
# uniform height for both was cramping the button/checkbox against
# the row edges.
INSTRUMENT_ROW_HEIGHT = 44


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MidiDivisi")
        self.resize(900, 650)

        # Holds the current Session (Track/Group/Instrument data), the
        # score currently in use (either the user's original MusicXML
        # from Import, or the temp-extracted copy from Open Session -
        # either way, "the file to re-embed if Save Session runs"),
        # and the .mididivisi file this session is currently
        # associated with (None until saved/loaded at least once -
        # Save Session behaves like Save Session As the first time).
        self.session = None
        self.loaded_file_path = None
        self.session_file_path = None
        self.profile_manager_window = None  # created lazily on first open, then reused

        # Chronological list of currently-checked QTreeWidgetItems -
        # tracked explicitly (not derived by re-scanning the tree)
        # because "first checked" determines the resulting name on
        # merge, and that's about click ORDER, not tree position.
        self.check_order = []

        self._build_menu_bar()
        self._build_toolbar()
        self._build_tree()
        self.statusBar()  # instantiates the status bar

        # Drag-and-drop MusicXML/session files onto the window.
        # Enabling this on the top-level window alone is enough -
        # child widgets (buttons, the tree) that haven't opted into
        # drops themselves are transparent to Qt's drag-and-drop
        # system, so events fall through to the nearest ancestor that
        # does accept them. Works over both the empty-state canvas
        # and the tree view, not just one or the other.
        self.setAcceptDrops(True)

    def _build_menu_bar(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("File")

        self.open_action = QAction("Import", self)
        self.open_action.triggered.connect(self.load_musicxml)
        file_menu.addAction(self.open_action)

        file_menu.addSeparator()

        self.open_session_action = QAction("Open Session", self)
        self.open_session_action.triggered.connect(self.open_session)
        file_menu.addAction(self.open_session_action)

        self.save_session_action = QAction("Save Session", self)
        self.save_session_action.triggered.connect(self.save_session)
        self.save_session_action.setEnabled(False)
        file_menu.addAction(self.save_session_action)

        self.save_session_as_action = QAction("Save Session As...", self)
        self.save_session_as_action.triggered.connect(self.save_session_as)
        self.save_session_as_action.setEnabled(False)
        file_menu.addAction(self.save_session_as_action)

        file_menu.addSeparator()

        self.close_file_action = QAction("Close File", self)
        self.close_file_action.triggered.connect(self.close_file)
        self.close_file_action.setEnabled(False)
        file_menu.addAction(self.close_file_action)

        file_menu.addSeparator()

        self.export_action = QAction("Export", self)
        self.export_action.triggered.connect(self.open_export_dialog)
        self.export_action.setEnabled(False)
        file_menu.addAction(self.export_action)

        file_menu.addSeparator()

        self.settings_action = QAction("Settings", self)
        self.settings_action.triggered.connect(self.open_settings_dialog)
        file_menu.addAction(self.settings_action)  # always enabled - not tied to a loaded score

        profiles_menu = menu_bar.addMenu("Profiles")

        profile_manager_action = QAction("Profile Manager", self)
        profile_manager_action.triggered.connect(self.open_profile_manager)
        profiles_menu.addAction(profile_manager_action)  # always enabled - not tied to a loaded score

        help_menu = menu_bar.addMenu("Help")

        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)

    def _build_toolbar(self):
        toolbar = self.addToolBar("Main")
        toolbar.setMovable(False)

        self.merge_action = QAction("Merge", self)
        self.merge_action.triggered.connect(self.merge_selected)
        self.merge_action.setEnabled(False)
        toolbar.addAction(self.merge_action)

        self.auto_merge_action = QAction("Auto Merge", self)
        self.auto_merge_action.triggered.connect(self.auto_merge)
        self.auto_merge_action.setEnabled(False)
        toolbar.addAction(self.auto_merge_action)

        self.merge_accents_action = QAction("Merge Accents", self)
        self.merge_accents_action.triggered.connect(self.merge_accents)
        self.merge_accents_action.setEnabled(False)
        toolbar.addAction(self.merge_accents_action)

        self.rename_action = QAction("Rename", self)
        self.rename_action.triggered.connect(self.rename_selected)
        self.rename_action.setEnabled(False)
        toolbar.addAction(self.rename_action)

        # Spacer pushes everything after it to the far right of the
        # toolbar. Export/Settings reuse the SAME QAction objects
        # already created in _build_menu_bar (not new ones) - Qt
        # keeps an action's enabled state and behavior in sync
        # automatically across every place it's added, so there's no
        # duplicate logic to maintain between the menu and toolbar
        # copies. Plain text for now - icons planned later (per
        # request), which will matter more here since these two will
        # eventually be icon-only to save space.
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        # The app-wide QWidget {background: ...} rule in theme.py
        # (added for scroll-area content) would otherwise paint this
        # spacer a different shade than the toolbar around it -
        # explicit instance-level stylesheet overrides that.
        spacer.setStyleSheet("background: transparent;")
        toolbar.addWidget(spacer)

        toolbar.addAction(self.export_action)
        toolbar.addAction(self.settings_action)

    def _build_tree(self):
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Track", "Merged", "Profile", "KS"])
        self.tree.setColumnWidth(COL_NAME, 500)
        self.tree.setColumnWidth(COL_PROFILE, 200)
        # Checkboxes are the selection mechanism here, not native row
        # highlighting - disable native selection so the two don't
        # visually compete with each other.
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.NoSelection)
        self.tree.itemChanged.connect(self.on_item_changed)
        self.tree.itemDoubleClicked.connect(self.on_item_double_clicked)

        self.empty_state_widget = self._build_empty_state()

        # Central widget swaps between the empty-state canvas (two big
        # Open/Import buttons) and the tree, rather than the tree
        # always being visible even with nothing loaded.
        self.central_stack = QStackedWidget()
        self.central_stack.addWidget(self.empty_state_widget)
        self.central_stack.addWidget(self.tree)
        self.central_stack.setCurrentWidget(self.empty_state_widget)
        self.setCentralWidget(self.central_stack)

    def _build_empty_state(self):
        """Blank-canvas view shown before anything is loaded: two big
        buttons (Open session / Import MusicXML), centered. Plain
        text for now - icons planned later (per request).
        """
        widget = QWidget()
        outer = QVBoxLayout(widget)
        outer.addStretch(1)

        button_row = QHBoxLayout()
        button_row.addStretch(1)

        open_button = QPushButton("Open")
        open_button.setFixedSize(160, 50)
        open_button.setToolTip("Open session")
        open_button.clicked.connect(self.open_session)
        button_row.addWidget(open_button)

        import_button = QPushButton("Import")
        import_button.setFixedSize(160, 50)
        import_button.setToolTip("Import MusicXML")
        import_button.clicked.connect(self.load_musicxml)
        button_row.addWidget(import_button)

        button_row.addStretch(1)
        outer.addLayout(button_row)
        outer.addStretch(1)

        return widget

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
            instrument_item.setSizeHint(COL_NAME, QSize(0, INSTRUMENT_ROW_HEIGHT))

            if instrument.is_merged:
                instrument_item.setText(COL_MERGED, "M")
                tooltip = "Merged from: " + ", ".join(
                    i.name for i in instrument.identities
                )
                instrument_item.setToolTip(COL_MERGED, tooltip)

            # Profile selection and KS toggle are only meaningful per
            # INSTRUMENT (never per-group), so these two columns are
            # only populated on the instrument row, via embedded real
            # widgets (setItemWidget) rather than tree text/checkbox -
            # a plain button/checkbox is a much simpler way to get
            # click behavior on one specific cell than custom painting.
            #
            # setItemWidget stretches whatever widget it's given to
            # fill the ENTIRE row height, ignoring that widget's own
            # setFixedHeight - confirmed directly (growing the row
            # grew the button along with it, not just the row). The
            # fix is to embed a WRAPPER with vertical stretch above/
            # below the real control, so the wrapper absorbs the
            # forced stretch instead of the button/checkbox itself.
            fixed_height = INSTRUMENT_ROW_HEIGHT - 16

            profile_button = QPushButton(
                instrument.profile.name if instrument.profile else "Click to select profile"
            )
            profile_button.setFixedHeight(fixed_height)
            profile_button.clicked.connect(
                lambda _, i=instrument: self.open_profile_picker(i)
            )
            profile_wrapper = QWidget()
            profile_wrapper.setStyleSheet("background: transparent;")
            profile_layout = QVBoxLayout(profile_wrapper)
            profile_layout.setContentsMargins(0, 0, 0, 0)
            profile_layout.addStretch(1)
            profile_layout.addWidget(profile_button)
            profile_layout.addStretch(1)
            self.tree.setItemWidget(instrument_item, COL_PROFILE, profile_wrapper)

            # KS is only shown at all when it's actually applicable -
            # HIDDEN, not just disabled, when no profile is assigned
            # or the assigned profile has no keyswitch defined. An
            # empty cell reads more clearly than a permanently-greyed-
            # out control for something that isn't in play.
            if instrument.profile is not None and instrument.profile.has_keyswitches:
                ks_checkbox = QCheckBox("KS")
                ks_checkbox.setFixedHeight(fixed_height)
                ks_checkbox.setChecked(instrument.keyswitch_enabled)
                ks_checkbox.toggled.connect(
                    lambda checked, i=instrument: self.on_keyswitch_toggled(i, checked)
                )
                ks_wrapper = QWidget()
                ks_wrapper.setStyleSheet("background: transparent;")
                ks_layout = QVBoxLayout(ks_wrapper)
                ks_layout.setContentsMargins(0, 0, 0, 0)
                ks_layout.addStretch(1)
                ks_layout.addWidget(ks_checkbox)
                ks_layout.addStretch(1)
                self.tree.setItemWidget(instrument_item, COL_KS, ks_wrapper)

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

                # Show the keyswitch note for this specific
                # articulation - but ONLY when the instrument's own KS
                # export toggle is actually on, not just whenever the
                # profile theoretically supports keyswitching. Showing
                # a note that isn't actually going to be used at
                # export would be misleading.
                if (
                    group.profile_item is not None
                    and instrument.profile is not None
                    and instrument.profile.keyswitch_enabled
                    and instrument.keyswitch_enabled
                    and group.profile_item.keyswitch_note is not None
                ):
                    group_item.setText(COL_KS, midi_note_name(group.profile_item.keyswitch_note))

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

    # --- Drag and drop -----------------------------------------------------

    MUSICXML_EXTENSIONS = (".xml", ".musicxml", ".mxl")
    SESSION_EXTENSION = ".mididivisi"

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = url.toLocalFile().lower()
                if path.endswith(self.MUSICXML_EXTENSIONS) or path.endswith(self.SESSION_EXTENSION):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if not urls:
            event.ignore()
            return

        path = urls[0].toLocalFile()
        lower = path.lower()

        if lower.endswith(self.SESSION_EXTENSION):
            self._open_session_path(path)
            event.acceptProposedAction()
        elif lower.endswith(self.MUSICXML_EXTENSIONS):
            self._import_musicxml_path(path)
            event.acceptProposedAction()
        else:
            event.ignore()

    # --- Toolbar actions ---------------------------------------------------

    def close_file(self):
        if self.session is None:
            return

        self.session = None
        self.loaded_file_path = None
        self.session_file_path = None
        self.check_order = []

        self.tree.clear()

        self.export_action.setEnabled(False)
        self.auto_merge_action.setEnabled(False)
        self.merge_accents_action.setEnabled(False)
        self.save_session_action.setEnabled(False)
        self.save_session_as_action.setEnabled(False)
        self.close_file_action.setEnabled(False)
        self.merge_action.setEnabled(False)
        self.rename_action.setEnabled(False)

        self.central_stack.setCurrentWidget(self.empty_state_widget)
        self._update_window_title()
        self.statusBar().showMessage("Closed file", 3000)

    def _update_window_title(self):
        """A session file (if one is associated) takes priority over
        the raw MusicXML filename - once a session's been saved to or
        loaded from a .mididivisi file, that's "the file" as far as
        the user is concerned, even though loaded_file_path also
        still points at the underlying score. Session names show
        without their extension; MusicXML names show with theirs (the
        distinction requested: "Song.mxml" style for a bare import,
        just the session name with no extension once it's a session).
        """
        if self.session_file_path:
            base = os.path.splitext(os.path.basename(self.session_file_path))[0]
            self.setWindowTitle(f"MidiDivisi - {base}")
        elif self.loaded_file_path:
            base = os.path.basename(self.loaded_file_path)
            self.setWindowTitle(f"MidiDivisi - {base}")
        else:
            self.setWindowTitle("MidiDivisi")

    def show_about_dialog(self):
        from PyQt6.QtCore import QT_VERSION_STR

        QMessageBox.about(
            self,
            "About MidiDivisi",
            "<h3>MidiDivisi</h3>"
            "<p>Created by Midori Builds</p>"
            "<p><a href='https://github.com/midori-builds/MidiDivisi'>"
            "github.com/midori-builds/MidiDivisi</a></p>"
            f"<p>Qt version: {QT_VERSION_STR}</p>",
        )

    def load_musicxml(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open / Import MusicXML",
            "",
            "MusicXML Files (*.xml *.musicxml *.mxl);;All Files (*)",
        )

        if not file_path:
            return  # user cancelled the dialog

        self._import_musicxml_path(file_path)

    def _import_musicxml_path(self, file_path):
        """The actual MusicXML-loading logic, given a path - shared by
        the Import dialog and drag-and-drop, so there's one code path
        for "load this file" regardless of how the path was obtained.
        """
        try:
            score = load_score(file_path)
        except Exception as e:
            QMessageBox.critical(self, "Failed to load file", str(e))
            return

        self.session = Session.from_score(score)
        self.loaded_file_path = file_path
        self.session_file_path = None  # fresh Import - no associated session file yet

        self.export_action.setEnabled(True)
        self.auto_merge_action.setEnabled(True)
        self.merge_accents_action.setEnabled(True)
        self.save_session_action.setEnabled(True)
        self.save_session_as_action.setEnabled(True)
        self.close_file_action.setEnabled(True)

        self.refresh_tree()
        self.central_stack.setCurrentWidget(self.tree)
        self._update_window_title()
        self.statusBar().showMessage(
            f"Loaded: {os.path.basename(file_path)} "
            f"({len(self.session.instruments)} instrument(s), "
            f"{len(self.session.tracks)} track(s))",
            6000,
        )

    def open_session(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Session",
            "",
            "MidiDivisi Session Files (*.mididivisi);;All Files (*)",
        )

        if not file_path:
            return  # user cancelled the dialog

        self._open_session_path(file_path)

    def _open_session_path(self, file_path):
        """The actual session-loading logic, given a path - shared by
        the Open Session dialog and drag-and-drop.
        """
        try:
            load_result = session_file.start_loading_session(file_path)
        except Exception as e:
            QMessageBox.critical(self, "Failed to open session", str(e))
            return

        use_saved_settings = False
        if load_result.settings_differ:
            box = QMessageBox(self)
            box.setWindowTitle("Settings differ")
            box.setText(
                "This session was saved with different Settings "
                "(keyword mapping / dynamics mapping / accent "
                "multiplier) than your current ones. Which should be "
                "used to load it?"
            )
            use_saved_button = box.addButton("Use Saved Settings", QMessageBox.ButtonRole.AcceptRole)
            box.addButton("Use Current Settings", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            use_saved_settings = box.clickedButton() is use_saved_button

        try:
            new_session, warnings = session_file.finish_loading_session(
                load_result, use_saved_settings
            )
        except Exception as e:
            QMessageBox.critical(self, "Failed to open session", str(e))
            return

        self.session = new_session
        self.loaded_file_path = load_result.temp_score_path
        self.session_file_path = file_path

        self.export_action.setEnabled(True)
        self.auto_merge_action.setEnabled(True)
        self.merge_accents_action.setEnabled(True)
        self.save_session_action.setEnabled(True)
        self.save_session_as_action.setEnabled(True)
        self.close_file_action.setEnabled(True)

        self.refresh_tree()
        self.central_stack.setCurrentWidget(self.tree)
        self._update_window_title()

        message = f"Opened session: {os.path.basename(file_path)}"
        if warnings:
            message += f" ({len(warnings)} item(s) from the saved session were skipped)"
        self.statusBar().showMessage(message, 6000)

        if warnings:
            QMessageBox.warning(
                self,
                "Some items were skipped",
                "The following items from the saved session no longer "
                "match the score and were skipped:\n\n" + "\n".join(warnings),
            )

    def save_session(self):
        if self.session is None:
            return

        if self.session_file_path is None:
            self.save_session_as()
            return

        try:
            session_file.save_session(
                self.session, self.loaded_file_path, self.session_file_path
            )
        except Exception as e:
            QMessageBox.critical(self, "Failed to save session", str(e))
            return

        self.statusBar().showMessage(
            f"Session saved: {os.path.basename(self.session_file_path)}", 5000
        )

    def save_session_as(self):
        if self.session is None:
            return

        default_name = "session.mididivisi"
        if self.loaded_file_path:
            base = os.path.splitext(os.path.basename(self.loaded_file_path))[0]
            default_name = f"{base}.mididivisi"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Session As",
            default_name,
            "MidiDivisi Session Files (*.mididivisi)",
        )

        if not file_path:
            return  # user cancelled the dialog

        if not file_path.lower().endswith(".mididivisi"):
            file_path += ".mididivisi"

        try:
            session_file.save_session(self.session, self.loaded_file_path, file_path)
        except Exception as e:
            QMessageBox.critical(self, "Failed to save session", str(e))
            return

        self.session_file_path = file_path
        self._update_window_title()
        self.statusBar().showMessage(f"Session saved: {os.path.basename(file_path)}", 5000)

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

    def merge_accents(self):
        """Auto-merge any Accent-variant group into its corresponding
        base technique, per instrument (e.g. "Staccato+Accent" folds
        into "Staccato"). StrongAccent (marcato) is deliberately left
        alone - see Session.merge_accent_variants for why. Runs
        immediately when clicked, same as Auto Merge - no selection
        required first, this is a whole-session action.
        """
        if self.session is None:
            return

        merged_count = self.session.merge_accent_variants()

        if merged_count:
            self.statusBar().showMessage(
                f"Merged {merged_count} accented group(s) into their base technique", 5000
            )
        else:
            self.statusBar().showMessage("Merge Accents: nothing to merge", 4000)

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

    def open_profile_manager(self):
        # Kept as an instance attribute (not a local variable) - a
        # standalone, non-modal QMainWindow with no other reference
        # holder would otherwise be garbage-collected the moment this
        # method returns, closing the window immediately. Reused
        # across multiple opens rather than creating a new instance
        # every time, so it doesn't lose whatever the user had
        # selected/expanded last time they had it open.
        if self.profile_manager_window is None:
            self.profile_manager_window = ProfileManagerWindow(parent=self)
            self.profile_manager_window.profiles_changed.connect(self.on_profiles_changed)
        self.profile_manager_window.show()
        self.profile_manager_window.raise_()
        self.profile_manager_window.activateWindow()

    def on_profiles_changed(self):
        """Called whenever the Profile Manager (a separate window)
        saves any change - keeps the main tree from going stale (e.g.
        showing a KS checkbox as absent when a profile's keyswitching
        was just turned on elsewhere). No-op if nothing's loaded.
        """
        if self.session is not None:
            self.refresh_tree()

    def open_profile_picker(self, instrument):
        dialog = ProfilePickerDialog(instrument.name, instrument.profile, parent=self)
        result = dialog.exec()

        if dialog.open_manager_requested:
            self.open_profile_manager()
            return

        if result != dialog.DialogCode.Accepted:
            return  # cancelled

        if dialog.clear_requested:
            instrument.profile = None
            instrument.keyswitch_enabled = False
            self.statusBar().showMessage(f"Cleared profile from: {instrument.name}", 4000)
        elif dialog.selected_profile is not None:
            self.session.apply_profile(instrument.id, dialog.selected_profile)
            self.statusBar().showMessage(
                f"Applied profile '{dialog.selected_profile.name}' to: {instrument.name}", 4000
            )

        self.refresh_tree()

    def on_keyswitch_toggled(self, instrument, checked):
        instrument.keyswitch_enabled = checked
        # Refresh so the group rows' KS-column note-name display
        # (gated on this same flag) updates immediately, rather than
        # staying stale until some unrelated action happens to
        # trigger a rebuild.
        self.refresh_tree()

