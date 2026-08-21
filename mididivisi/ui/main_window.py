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

from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtGui import QAction, QColor
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
    QLabel,
    QApplication,
)

from mididivisi.core.parser import load_score
from mididivisi.core.session import Session
from mididivisi.core import session_file
from mididivisi.core.midifi import detect_midifiable_content
from mididivisi.ui.export_dialog import ExportDialog
from mididivisi.ui.settings_dialog import SettingsDialog
from mididivisi.ui.profile_manager import ProfileManagerWindow
from mididivisi.ui.notation_preview_window import NotationPreviewWindow
from mididivisi.ui.midifi_dialog import MidifiDialog
from mididivisi.ui.profile_picker_dialog import ProfilePickerDialog
from mididivisi.core.profiles import midi_note_name
from mididivisi.ui.theme import COLORS

# Tree column indices
COL_NAME = 0
COL_MERGED = 1
COL_PROFILE = 2
COL_KS = 3
COL_PREVIEW = 4
COL_MIDIFI = 5

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
        self.notation_preview_windows = []  # each Preview click opens a NEW independent
                                             # window (unlike Profile Manager) - held here
                                             # so they aren't garbage-collected immediately

        # Chronological list of currently-checked QTreeWidgetItems -
        # tracked explicitly (not derived by re-scanning the tree)
        # because "first checked" determines the resulting name on
        # merge, and that's about click ORDER, not tree position.
        self.check_order = []

        # Support for "click anywhere on a row toggles its checkbox"
        # (see on_tree_item_clicked) - a row's own tiny checkbox glyph
        # remains clickable too (Qt's native behavior), which creates
        # a real double-toggle risk if not guarded against: verified
        # directly that a glyph click fires itemChanged BEFORE
        # itemClicked, so this flag records "a genuine check-state
        # toggle (not a text rename) just happened via itemChanged"
        # for the immediately-following itemClicked to consume and
        # skip re-toggling.
        self._just_toggled_via_indicator = None

        # Set while our OWN programmatic setCheckState calls are in
        # flight - a real bug this caught directly (not theoretical):
        # without it, our own call ALSO fires itemChanged, which would
        # incorrectly set the glyph-click guard above even though no
        # itemClicked is coming to ever consume it - leaving a stale
        # guard that silently eats the next real click on that row
        # entirely. Lets on_item_changed tell the two sources apart.
        self._programmatic_toggle_in_progress = False

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
        file_menu.setFixedWidth(150)

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
        profiles_menu.setFixedWidth(125)

        profile_manager_action = QAction("Profile Manager", self)
        profile_manager_action.triggered.connect(self.open_profile_manager)
        profiles_menu.addAction(profile_manager_action)  # always enabled - not tied to a loaded score

        midifi_menu = menu_bar.addMenu("Midi-fy")
        midifi_menu.setFixedWidth(90)

        self.midifi_dialog_action = QAction("Midi-fy...", self)
        self.midifi_dialog_action.triggered.connect(self.open_midifi_dialog)
        self.midifi_dialog_action.setEnabled(False)  # needs a loaded session's file path to rebuild against
        midifi_menu.addAction(self.midifi_dialog_action)

        help_menu = menu_bar.addMenu("Help")
        help_menu.setFixedWidth(78)

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

        self.merge_midifi_action = QAction("Merge Midi-fy", self)
        self.merge_midifi_action.triggered.connect(self.merge_midifi)
        self.merge_midifi_action.setEnabled(False)
        toolbar.addAction(self.merge_midifi_action)

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

    def _build_midifi_notice_banner(self):
        """A dismissible, non-blocking notice shown after import if
        the score has content midi-fy could apply to (currently just
        tremolo) - the user might have no idea this feature exists,
        but a modal popup felt too intrusive for something that
        shouldn't take away the choice of WHEN to engage with it (per
        design discussion). Reuses the theme's own accent color for
        consistency rather than inventing a new one.
        """
        banner = QWidget()
        banner.setStyleSheet(
            f"background: {COLORS['accent']}; color: {COLORS['accent_text']};"
        )
        layout = QHBoxLayout(banner)
        layout.setContentsMargins(12, 8, 12, 8)

        self.midifi_notice_label = QLabel("")
        self.midifi_notice_label.setWordWrap(True)
        self.midifi_notice_label.setStyleSheet(f"color: {COLORS['accent_text']};")
        layout.addWidget(self.midifi_notice_label, 1)

        open_button = QPushButton("Open Midi-fy")
        open_button.clicked.connect(self._on_midifi_notice_open_clicked)
        layout.addWidget(open_button)

        dismiss_button = QPushButton("Dismiss")
        dismiss_button.clicked.connect(self._dismiss_midifi_notice)
        layout.addWidget(dismiss_button)

        banner.setVisible(False)
        return banner

    def _on_midifi_notice_open_clicked(self):
        self.midifi_notice_banner.setVisible(False)
        self.open_midifi_dialog()

    def _dismiss_midifi_notice(self):
        self.midifi_notice_banner.setVisible(False)

    def _check_midifi_notice(self, file_path):
        """Called right after a fresh MusicXML import - shows the
        banner if the score has midi-fiable content, using a
        lightweight independent detection pass (see
        midifi.detect_midifiable_content) rather than inspecting the
        already-loaded session, which would either over- or under-
        count depending on what the active config already did to the
        notes. Per-import, not a permanent one-time-ever notice - re-
        shows on the next import if relevant again, doesn't nag
        further within the same session once dismissed.
        """
        try:
            detected = detect_midifiable_content(file_path)
        except Exception:
            return  # detection failing shouldn't block a successful import

        if not detected:
            self.midifi_notice_banner.setVisible(False)
            return

        tremolo_count = detected.get("tremolo", 0)
        if tremolo_count:
            noun = "passage" if tremolo_count == 1 else "passages"
            self.midifi_notice_label.setText(
                f"This score has {tremolo_count} tremolo {noun} that Midi-fy can turn "
                f"into real notes for libraries without a tremolo patch."
            )
            self.midifi_notice_banner.setVisible(True)

    def _build_tree(self):
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Track", "Merged", "Profile", "KS", "Preview", "Midi-fy"])
        self.tree.setColumnWidth(COL_NAME, 450)
        self.tree.setColumnWidth(COL_MERGED, 65)
        self.tree.setColumnWidth(COL_PROFILE, 170)
        self.tree.setColumnWidth(COL_KS, 35)
        self.tree.setColumnWidth(COL_PREVIEW, 65)
        self.tree.setColumnWidth(COL_MIDIFI, 55)
        # Checkboxes are the selection mechanism here, not native row
        # highlighting - disable native selection so the two don't
        # visually compete with each other.
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.NoSelection)
        self.tree.itemChanged.connect(self.on_item_changed)
        self.tree.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.tree.itemClicked.connect(self.on_tree_item_clicked)

        self.empty_state_widget = self._build_empty_state()
        self.midifi_notice_banner = self._build_midifi_notice_banner()

        # Central widget swaps between the empty-state canvas (two big
        # Open/Import buttons) and the tree (now wrapped with the
        # notice banner above it), rather than the tree always being
        # visible even with nothing loaded.
        tree_container = QWidget()
        tree_layout = QVBoxLayout(tree_container)
        tree_layout.setContentsMargins(0, 0, 0, 0)
        tree_layout.setSpacing(0)
        tree_layout.addWidget(self.midifi_notice_banner)
        tree_layout.addWidget(self.tree, 1)
        self.tree_container = tree_container

        self.central_stack = QStackedWidget()
        self.central_stack.addWidget(self.empty_state_widget)
        self.central_stack.addWidget(tree_container)
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
        # A full clear()+rebuild naturally resets scroll to the top,
        # since a freshly-cleared widget has no scroll state at all -
        # capture and restore it explicitly so routine actions (merge,
        # KS toggle, etc.) don't keep kicking the view back to the top
        # on a large score.
        scroll_position = self.tree.verticalScrollBar().value()

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

            # Notation Preview - crude v1, per instrument. Always
            # available (doesn't depend on a profile being assigned),
            # only needs the original score's file path, which is why
            # this is disabled entirely if the session was somehow
            # created without one (shouldn't normally happen given how
            # load/import work, but defensive rather than crashing).
            # TODO replace with preview icon
            preview_button = QPushButton("P")
            preview_button.setFixedHeight(fixed_height)
            preview_button.clicked.connect(
                lambda _, i=instrument: self.open_notation_preview(i)
            )
            preview_wrapper = QWidget()
            preview_wrapper.setStyleSheet("background: transparent;")
            preview_layout = QVBoxLayout(preview_wrapper)
            preview_layout.setContentsMargins(0, 0, 0, 0)
            preview_layout.addStretch(1)
            preview_layout.addWidget(preview_button)
            preview_layout.addStretch(1)
            self.tree.setItemWidget(instrument_item, COL_PREVIEW, preview_wrapper)

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

                # Flag articulations the assigned profile doesn't
                # cover - blue (not red, which would read as an error)
                # with a tooltip explaining why. Reuses the theme's
                # own accent blue for consistency rather than an
                # arbitrary color. Only applies once a profile is
                # actually assigned - an instrument with no profile at
                # all has nothing to be "missing" from.
                if instrument.profile is not None and group.profile_item is None:
                    group_item.setForeground(COL_NAME, QColor("#3584E4"))
                    group_item.setToolTip(COL_NAME, "Missing in profile")

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

                # Midi-fy toggle - INSTANT (no rebuild warning, unlike
                # the tremolo threshold - see core/midifi.py and
                # Track.get_active_notes). Only shown for a genuine
                # group whose content this feature actually applies
                # to - checked against the underlying Track's
                # immutable .label (not group.name, which the user may
                # have renamed) so detection never breaks from a
                # rename. Hidden entirely (not just disabled) for
                # anything else, same "empty cell reads clearer than a
                # permanently-greyed control" convention already used
                # for KS.
                #
                # Arpeggio deliberately has NO checkbox here at all -
                # unlike trill/tremolo spanner, there's no known
                # sample-library case where a per-passage opt-out
                # would matter, so it's controlled by one global
                # setting in the Midi-fy dialog instead. It DOES still
                # get its own separate "Midifi+X" track, though,
                # exactly matching tremolo's own labeling convention
                # (see parser.get_note_level_label and
                # MIDIFI_SOURCE_LABEL_PREFIX) - a real, deliberate
                # design choice, not an oversight: an earlier version
                # of this removed arpeggio's label entirely, folding
                # it invisibly into its base articulation's group, but
                # that made it impossible to see or merge on purpose -
                # the user explicitly wants the separate track back,
                # mergeable via the SAME "Merge Midi-fy" button that
                # already handles tremolo, or via a regular manual
                # merge, exactly as they choose. The one real
                # difference from tremolo's own use of this label:
                # tremolo's "Midifi+X" means the note has ALREADY been
                # destructively realized by the time that label exists;
                # arpeggio's means the note WILL BE realized if the
                # global setting is on - the underlying note itself
                # stays completely untouched either way, computed
                # fresh on demand exactly like trill.
                label = group.tracks[0].label
                # Checking against EVERY track in the group (not just
                # the first) is what correctly handles a merged group
                # - confirmed directly that merging combines matching-
                # label groups together (e.g. both staves of a grand-
                # staff harp end up with matching-labeled tracks), so
                # there's no ambiguity about what a single checkbox
                # should control.
                all_same_label = all(t.label == label for t in group.tracks)
                is_trill = all_same_label and "Trill" in label
                is_tremolo_spanner = all_same_label and "Tremolo-" in label

                if is_trill or is_tremolo_spanner:
                    tracks = group.tracks
                    midifi_checkbox = QCheckBox()
                    midifi_checkbox.setFixedHeight(ROW_HEIGHT - 8)
                    # Checked only if EVERY track in the group is
                    # currently toggled on - a simple, unambiguous
                    # state for the common case (all tracks toggled
                    # together, matching how a user would naturally
                    # expect one checkbox to behave for a merged row)
                    # rather than a three-state partial indicator,
                    # which would be more correct for a mixed state
                    # but adds real complexity for something that
                    # shouldn't come up often in practice.
                    midifi_checkbox.setChecked(all(t.midifi_toggle_active for t in tracks))
                    if is_trill:
                        midifi_checkbox.setToolTip(
                            "Realize this trill into alternating notes "
                            "(for libraries without a dedicated trill patch)"
                        )
                    else:
                        midifi_checkbox.setToolTip(
                            "On: alternate between the tremolo's two written "
                            "sides. Off (default): one sustained note/chord "
                            "for a dedicated tremolo/roll patch."
                        )
                    midifi_checkbox.toggled.connect(
                        lambda checked, ts=tracks: self.on_midifi_toggled(ts, checked)
                    )
                    midifi_wrapper = QWidget()
                    midifi_wrapper.setStyleSheet("background: transparent;")
                    midifi_layout = QVBoxLayout(midifi_wrapper)
                    midifi_layout.setContentsMargins(0, 0, 0, 0)
                    midifi_layout.addStretch(1)
                    midifi_layout.addWidget(midifi_checkbox)
                    midifi_layout.addStretch(1)
                    self.tree.setItemWidget(group_item, COL_MIDIFI, midifi_wrapper)

        self.tree.expandAll()
        self.tree.blockSignals(False)
        self.update_action_states()
        self.tree.verticalScrollBar().setValue(scroll_position)

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
        # land in this same signal. This is also the FULL story of
        # what could have changed here (COL_NAME's data is only ever
        # text or check-state) - so if it WASN'T a rename, it must
        # have been a check-state toggle.
        new_text = item.text(COL_NAME)
        is_rename = new_text != obj.name and new_text.strip()

        if is_rename:
            obj.rename(new_text)
            self.statusBar().showMessage(f"Renamed to: {new_text}", 4000)
        else:
            # A genuine check-state toggle, not a rename - if this was
            # triggered by clicking the tiny checkbox glyph directly,
            # an itemClicked for the SAME click is about to fire right
            # after this (verified directly: itemChanged fires BEFORE
            # itemClicked for a glyph click) - flag it so
            # on_tree_item_clicked knows not to ALSO toggle it again,
            # which would otherwise make the glyph appear to do
            # nothing (toggle, then immediately un-toggle).
            #
            # Deliberately NOT set for our OWN programmatic toggle (see
            # _programmatic_toggle_in_progress) - no itemClicked is
            # ever coming to consume it in that case, and setting it
            # anyway would leave a stale guard that silently swallows
            # the next real click on this row. Found this exact bug
            # directly via testing, not theoretically - a second click
            # on an already-toggled row was doing nothing at all.
            if not self._programmatic_toggle_in_progress:
                self._just_toggled_via_indicator = item

        checked = item.checkState(COL_NAME) == Qt.CheckState.Checked
        if checked:
            if item not in self.check_order:
                self.check_order.append(item)
        else:
            if item in self.check_order:
                self.check_order.remove(item)

        # Visual highlight mirrors check state directly - deliberately
        # NOT using Qt's native row-selection mechanism for this (see
        # design discussion): a background color driven purely by
        # check state is simpler and can't drift out of sync with it,
        # since there's only ever one source of truth.
        highlight = QColor(COLORS["row_selected"]) if checked else QColor(COLORS["bg_content"])
        text_color = QColor(COLORS["accent_text"]) if checked else QColor(COLORS["text"])
        for col in (COL_NAME, COL_MERGED):
            item.setBackground(col, highlight)
            item.setForeground(col, text_color)

        self.update_action_states()

    def _enforce_replace_selection(self, item):
        """Uncheck every OTHER currently-checked row, leaving just
        `item` checked - the "plain click replaces the selection" half
        of standard multi-select semantics (Finder/Explorer-style):
        clicking a row selects ONLY that row unless a modifier key is
        held. Caller is responsible for ensuring `item` itself ends up
        checked - this only clears everything ELSE.

        Deliberately does NOT manage
        self._programmatic_toggle_in_progress itself - the one caller
        (on_tree_item_clicked) needs that flag held across BOTH this
        call AND its own subsequent "ensure item is checked" step as
        ONE single guarded block. Letting this method clear the flag
        at its own end would incorrectly re-enable the glyph-click
        guard partway through the caller's own still-in-progress
        programmatic changes - the exact same stale-guard bug pattern
        already found and fixed once before, reintroduced by having
        two nested scopes fight over one shared flag.
        """
        for other in list(self.check_order):
            if other is not item:
                other.setCheckState(COL_NAME, Qt.CheckState.Unchecked)

    def on_tree_item_clicked(self, item, column):
        """Standard, familiar multi-select semantics (Finder/Explorer-
        style), extended to work from ANYWHERE on a row (except
        another embedded control like the Profile button, KS/Midi-fy
        checkboxes, or Preview button), not just the tiny checkbox
        glyph - with a real, deliberate distinction between the two
        click targets, not one rule gated purely by modifier key:
        - The checkbox glyph itself: ALWAYS purely additive (toggles
          just this row, never touches anything else), REGARDLESS of
          whether Cmd/Ctrl is held. This is the entire point of the
          checkbox existing at all - a way to build a multi-selection
          without needing to hold a modifier key. Making it ALSO
          replace the selection sometimes would defeat that purpose.
        - Anywhere else on the row (name text, the Merged column):
          plain click replaces the selection (selects ONLY this row);
          Cmd/Ctrl-click toggles just this row instead, same as the
          glyph.

        Applied synchronously/immediately, deliberately NOT debounced
        - an earlier version delayed this by
        `QApplication.doubleClickInterval()` specifically to stop a
        double-click (rename/split) from ALSO toggling the checkbox on
        its first click, but that delay made every ordinary click feel
        noticeably laggy, for a problem that turns out to be harmless
        either way: a double-click-to-rename also leaving that row
        selected is a sensible outcome, not a confusing one, and a
        double-click-to-split (COL_MERGED) triggers a full
        refresh_tree() rebuild anyway, which wipes any selection
        regardless of what happened on the first click.

        One thing this STILL has to guard against, verified directly
        rather than assumed: itemClicked ALSO fires for a click that
        landed squarely on the checkbox glyph itself, AFTER Qt's own
        native handling already toggled it - naively toggling again
        here would cancel that back out. Guarded via
        self._just_toggled_via_indicator, set by on_item_changed.
        """
        if self._just_toggled_via_indicator is item:
            self._just_toggled_via_indicator = None
            return  # glyph click already toggled natively - always additive, nothing more to do

        if column not in (COL_NAME, COL_MERGED):
            return  # an embedded-widget column - let it handle its own click

        if not (item.flags() & Qt.ItemFlag.ItemIsUserCheckable):
            return

        modifiers = QApplication.keyboardModifiers()
        additive = bool(modifiers & Qt.KeyboardModifier.ControlModifier)

        self._programmatic_toggle_in_progress = True
        if additive:
            current = item.checkState(COL_NAME)
            new_state = (
                Qt.CheckState.Unchecked if current == Qt.CheckState.Checked else Qt.CheckState.Checked
            )
            item.setCheckState(COL_NAME, new_state)
        else:
            self._enforce_replace_selection(item)
            if item.checkState(COL_NAME) != Qt.CheckState.Checked:
                item.setCheckState(COL_NAME, Qt.CheckState.Checked)
        self._programmatic_toggle_in_progress = False

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
        self.merge_midifi_action.setEnabled(False)
        self.midifi_dialog_action.setEnabled(False)
        self.save_session_action.setEnabled(False)
        self.save_session_as_action.setEnabled(False)
        self.close_file_action.setEnabled(False)
        self.merge_action.setEnabled(False)
        self.rename_action.setEnabled(False)

        self.midifi_notice_banner.setVisible(False)
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
        self.merge_midifi_action.setEnabled(True)
        self.midifi_dialog_action.setEnabled(True)
        self.save_session_action.setEnabled(True)
        self.save_session_as_action.setEnabled(True)
        self.close_file_action.setEnabled(True)

        self.refresh_tree()
        self.central_stack.setCurrentWidget(self.tree_container)
        self._update_window_title()
        self._check_midifi_notice(file_path)
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
        self.merge_midifi_action.setEnabled(True)
        self.midifi_dialog_action.setEnabled(True)
        self.save_session_action.setEnabled(True)
        self.save_session_as_action.setEnabled(True)
        self.close_file_action.setEnabled(True)

        self.refresh_tree()
        self.central_stack.setCurrentWidget(self.tree_container)
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

    def merge_midifi(self):
        """Auto-merge any midi-fy-tagged group (e.g. a tremolo note
        realized into literal repeated notes) into its corresponding
        base technique, per instrument - same shape as Merge Accents,
        see Session.merge_midifi_variants.
        """
        if self.session is None:
            return

        merged_count = self.session.merge_midifi_variants()

        if merged_count:
            self.statusBar().showMessage(
                f"Merged {merged_count} midi-fied group(s) into their base technique", 5000
            )
        else:
            self.statusBar().showMessage("Merge Midi-fy: nothing to merge", 4000)

        self.refresh_tree()

    def open_midifi_dialog(self):
        """Opens the Midi-fy tool. What happens on confirm depends on
        WHICH setting changed - the dialog itself decides this (see
        MidifiDialog._apply / .requires_rebuild) and this handler just
        branches on it:
        - Tremolo threshold changed: full session rebuild, re-parses
          loaded_file_path fresh and replaces self.session entirely,
          discarding any manual customization since load (the dialog
          already warned about this before confirming). Consistent
          with how Profile reapplication already works.
        - Trill rate only: instant - just swaps in the new config and
          redraws the tree, no rebuild, no data loss, because trill
          realization is computed fresh on demand every time (see
          Track.get_active_notes) rather than baked in once.
        """
        if self.session is None or self.loaded_file_path is None:
            return

        dialog = MidifiDialog(self.session.midifi_config, parent=self)
        result = dialog.exec()

        if result != dialog.DialogCode.Accepted or dialog.result_config is None:
            return  # cancelled

        new_config = dialog.result_config

        if dialog.requires_rebuild:
            try:
                score = load_score(self.loaded_file_path, midifi_config=new_config)
            except Exception as e:
                QMessageBox.critical(self, "Failed to rebuild session", str(e))
                return

            self.session = Session.from_score(score, midifi_config=new_config)
            self.refresh_tree()
            self.statusBar().showMessage("Session rebuilt with updated Midi-fy settings", 5000)
        else:
            self.session.midifi_config = new_config
            self.refresh_tree()
            self.statusBar().showMessage("Midi-fy settings updated", 5000)

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

    def open_notation_preview(self, instrument):
        """Crude v1 - see notation_preview_window.py. Renders the
        instrument's real notation, extracted directly from the
        ORIGINAL score file (not reconstructed from our own flat
        Track/Group note data).

        For a MERGED instrument (2+ InstrumentIdentity), previews just
        the FIRST identity (same "first-selected" precedent already
        used for naming elsewhere) - a real, known limitation of this
        crude version, not a full multi-part combined view. Flagged
        clearly rather than silently only showing part of the story.
        """
        if self.loaded_file_path is None:
            QMessageBox.warning(
                self, "Preview unavailable", "No original score file is available for this session."
            )
            return

        identity = instrument.identities[0]
        window = NotationPreviewWindow(
            instrument.name, self.loaded_file_path, identity.natural_key, parent=self
        )
        window.show()
        self.notation_preview_windows.append(window)

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

    def on_midifi_toggled(self, tracks, checked):
        """Instant - just flips the flag(s) and redraws the tree, no
        rebuild-from-source warning. This is exactly the point of the
        non-destructive architecture built for trill, later
        generalized for tremolo spanner and arpeggio - Track.notes
        (the original) is never touched, so there's nothing to warn
        about losing. refresh_tree() here is a cheap UI-only redraw
        (walking the already-in-memory Session), not a re-parse - the
        same cost as any other tree refresh in this app, not the
        "rebuild from source" tremolo's THRESHOLD change triggers (a
        different, unrelated setting - single-note tremolo, not this
        toggle).

        Takes a LIST of tracks, not a single one - a merged group can
        legitimately hold several same-labeled tracks (e.g. both
        staves of a merged grand-staff harp, both tagged "Arpeggio"),
        and one checkbox correctly toggles ALL of them together in
        that case. An unmerged group just passes its own single-
        element track list, so this one code path handles both.

        Shared across every midi-fy-toggleable content type (trill,
        tremolo spanner, arpeggio) - what happens on toggle is generic
        (flip the flag(s)), it's Track.get_active_notes() that knows
        how to interpret the flag differently per content type.
        """
        for track in tracks:
            track.midifi_toggle_active = checked
        self.refresh_tree()

