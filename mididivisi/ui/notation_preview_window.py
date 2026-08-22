"""
Notation preview window - crude v1.

Deliberately minimal, per design discussion: no highlighting, no side
panel, no multi-select - just "show me the real notation for this one
instrument," which is the core value (seeing what the notation
software actually produced) without the polish planned for later
(see BACKLOG.md's "Notation preview" section for the fuller design).

Non-modal, spawnable multiple times - clicking Preview on several
instruments opens several independent windows, so they can be
compared side by side. This is what ruled out a single reused preview
window/dialog in the original design discussion.
"""

from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QScrollArea,
    QPushButton,
    QLabel,
    QMessageBox,
)
from PyQt6.QtSvgWidgets import QSvgWidget

from mididivisi.core.notation_preview import extract_part_xml, render_musicxml_to_svg_pages
from mididivisi.ui.theme import COLORS

# Bounds on manual zoom - generous enough to be useless in practice,
# just guarding against absurd/degenerate widget sizes.
MIN_ZOOM = 0.05
MAX_ZOOM = 5.0
ZOOM_STEP = 1.25


class NotationPreviewWindow(QMainWindow):
    def __init__(self, instrument_name, original_file_path, natural_key, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Notation Preview - {instrument_name}")
        self.resize(900, 700)

        self.pages = []
        self.current_page_index = 0
        self.zoom_factor = 1.0  # properly established by the one-time auto-fit in showEvent
        self.natural_size = None  # the current page's own intrinsic (unscaled) size
        self._has_auto_fitted = False

        self._build_ui()

        try:
            xml_string = extract_part_xml(original_file_path, natural_key)
            self.pages = render_musicxml_to_svg_pages(xml_string)
        except Exception as e:
            QMessageBox.critical(self, "Failed to render notation", str(e))
            return

        self._show_page(0)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        nav_row = QHBoxLayout()
        self.prev_button = QPushButton("< Previous")
        self.prev_button.clicked.connect(self.go_previous_page)
        nav_row.addWidget(self.prev_button)

        self.page_label = QLabel("")
        nav_row.addWidget(self.page_label)

        self.next_button = QPushButton("Next >")
        self.next_button.clicked.connect(self.go_next_page)
        nav_row.addWidget(self.next_button)

        nav_row.addStretch(1)

        zoom_out_button = QPushButton("-")
        zoom_out_button.setFixedWidth(30)
        zoom_out_button.clicked.connect(self.zoom_out)
        nav_row.addWidget(zoom_out_button)

        self.zoom_label = QLabel("100%")
        self.zoom_label.setFixedWidth(50)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav_row.addWidget(self.zoom_label)

        zoom_in_button = QPushButton("+")
        zoom_in_button.setFixedWidth(30)
        zoom_in_button.clicked.connect(self.zoom_in)
        nav_row.addWidget(zoom_in_button)

        fit_button = QPushButton("Fit to Window")
        fit_button.clicked.connect(self.zoom_fit)
        nav_row.addWidget(fit_button)

        layout.addLayout(nav_row)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(False)  # SVG has a real, scaled size - let it scroll, don't squash it
        # The global QScrollArea rule (theme.py) is deliberately
        # transparent everywhere else in the app, letting the dark
        # background show through - which makes Verovio's solid-black
        # notation nearly illegible here. Overridden directly on this
        # ONE widget, not globally, so every other scroll area in the
        # app keeps the normal dark theme. Both the QScrollArea AND
        # its viewport need this explicitly - a real Qt quirk, not
        # redundant: the viewport is a separate child widget that
        # doesn't reliably inherit a background set only on its parent.
        notation_bg_style = f"background-color: {COLORS['notation_bg']}; border: none;"
        self.scroll_area.setStyleSheet(notation_bg_style)
        self.scroll_area.viewport().setStyleSheet(notation_bg_style)
        self.svg_widget = QSvgWidget()
        self.scroll_area.setWidget(self.svg_widget)
        layout.addWidget(self.scroll_area, 1)

    def showEvent(self, event):
        super().showEvent(event)
        # The scroll area's viewport doesn't report a real size until
        # the window is ACTUALLY shown and laid out - computing "fit
        # to window" any earlier (e.g. in __init__) would use a stale
        # or default size, same class of gotcha as isVisible() needing
        # a real .show() elsewhere in this project. Only runs once,
        # establishing the initial view - not on every subsequent
        # show/restore, so it doesn't fight a zoom level the user
        # already chose.
        if not self._has_auto_fitted and self.natural_size is not None:
            self._has_auto_fitted = True
            self.zoom_fit()

    def _show_page(self, index):
        if not self.pages:
            return
        index = max(0, min(index, len(self.pages) - 1))
        self.current_page_index = index

        self.svg_widget.load(QByteArray(self.pages[index].encode("utf-8")))
        self.natural_size = self.svg_widget.sizeHint()
        # Preserves whatever zoom the user currently has (matches
        # normal document-viewer behavior - flipping pages shouldn't
        # reset your zoom level) rather than re-fitting on every page.
        self._apply_zoom()

        self.page_label.setText(f"Page {index + 1} of {len(self.pages)}")
        self.prev_button.setEnabled(index > 0)
        self.next_button.setEnabled(index < len(self.pages) - 1)

    def _apply_zoom(self):
        if self.natural_size is None or self.natural_size.width() <= 0:
            return
        new_width = max(1, int(self.natural_size.width() * self.zoom_factor))
        new_height = max(1, int(self.natural_size.height() * self.zoom_factor))
        self.svg_widget.resize(new_width, new_height)
        self.zoom_label.setText(f"{round(self.zoom_factor * 100)}%")

    def zoom_in(self):
        self.zoom_factor = min(self.zoom_factor * ZOOM_STEP, MAX_ZOOM)
        self._apply_zoom()

    def zoom_out(self):
        self.zoom_factor = max(self.zoom_factor / ZOOM_STEP, MIN_ZOOM)
        self._apply_zoom()

    def zoom_fit(self):
        """Scale so the WHOLE page fits within the current viewport,
        both dimensions - matches normal "fit page" behavior in
        document viewers, rather than fit-to-width (which would still
        leave a full page quite tall/scrolly).
        """
        if self.natural_size is None or self.natural_size.width() <= 0 or self.natural_size.height() <= 0:
            return
        viewport = self.scroll_area.viewport().size()
        if viewport.width() <= 0 or viewport.height() <= 0:
            return  # not usefully laid out yet - bail rather than compute nonsense
        scale_w = viewport.width() / self.natural_size.width()
        scale_h = viewport.height() / self.natural_size.height()
        # Slight margin so scrollbars don't immediately appear right at the fitted edge
        self.zoom_factor = min(scale_w, scale_h) * 0.98
        self._apply_zoom()

    def go_previous_page(self):
        self._show_page(self.current_page_index - 1)

    def go_next_page(self):
        self._show_page(self.current_page_index + 1)
