"""
MidiDivisi visual theme.

Flat, modern, warm/creamy palette rather than stark white - a
utility tool that isn't meant for long sittings, so this stays
simple: one palette, no dark mode/theme-switching infrastructure
(unlike Tako Reader, which is a long-session reading app where that
mattered). If a dark mode is ever wanted later, this is structured
close enough to Tako Reader's theme.py pattern (one dict of tokens,
one stylesheet-building function) that adding one would be a
straightforward extension, not a rewrite.
"""

COLORS = {
    "bg_app": "#20211F",
    "bg_toolbar": "#292A27",
    "bg_content": "#31322F",
    "border": "#45453F",
    "text": "#F0EDE5",
    "text_muted": "#B9B5AA",
    "hover": "#705F3D",
    "accent": "#B79A62",
    "row_selected" : "#574A2F",
    "accent_text": "#FFFFFF",
    "test_color": '#FF0000'
}


def build_stylesheet():
    c = COLORS
    return f"""
        QWidget {{
            background: {c['bg_app']};
            color: {c['text']};
        }}

        QMainWindow {{
            background: {c['bg_app']};
        }}

        QToolBar {{
            background: {c['bg_toolbar']};
            border: none;
            border-bottom: 1px solid {c['border']};
            padding: 4px;
            spacing: 4px;
        }}

        QToolButton {{
            background: transparent;
            color: {c['text']};
            border: 1px solid transparent;
            border-radius: 4px;
            padding: 6px 10px;
            font-size: 13px;
        }}

        QToolButton:hover {{
            background: {c['hover']};
            border: 1px solid {c['border']};
        }}

        QToolButton:pressed {{
            background: {c['accent']};
            color: {c['accent_text']};
        }}

        QToolButton:disabled {{
            color: {c['text_muted']};
        }}

        QTreeWidget {{
            background: {c['bg_content']};
            color: {c['text']};
            border: 1px solid {c['border']};
            border-radius: 4px;
            outline: none;
        }}

        QTreeWidget::item {{
            padding: 4px 2px;
        }}

        QTreeWidget::item:hover {{
            background: {c['hover']};
        }}

        QHeaderView::section {{
            background: {c['bg_toolbar']};
            color: {c['text']};
            border: none;
            border-bottom: 1px solid {c['border']};
            border-right: 1px solid {c['border']};
            font-size: 13px;
            padding: 6px 8px;
        }}

        QStatusBar {{
            background: {c['bg_toolbar']};
            color: {c['text_muted']};
            border-top: 1px solid {c['border']};
        }}

        QToolTip {{
            background: {c['text']};
            color: {c['bg_content']};
            border: none;
            padding: 4px 6px;
            border-radius: 3px;
        }}

        /* --- Dialogs (Settings, Export) and their contents. Without
           these, QDialog/QPushButton/QLineEdit/QListWidget all fall
           back to the OS-native look, since only QMainWindow/
           QToolBar/QTreeWidget were covered above - that's why
           dialogs previously looked like stock system dialogs
           instead of matching the rest of the app. */

        QDialog {{
            background: {c['bg_app']};
            color: {c['text']};
        }}

        QLabel {{
            color: {c['text']};
        }}

        QPushButton {{
            background: {c['bg_content']};
            color: {c['text']};
            border: 1px solid {c['border']};
            border-radius: 4px;
            padding: 6px 14px;
        }}

        QPushButton:hover {{
            background: {c['hover']};
        }}

        QPushButton:pressed {{
            background: {c['accent']};
            color: {c['accent_text']};
            border: 1px solid {c['accent']};
        }}

        QPushButton:disabled {{
            color: {c['text_muted']};
            background: {c['bg_toolbar']};
        }}

        QLineEdit {{
            background: {c['bg_content']};
            color: {c['text']};
            border: 1px solid {c['border']};
            border-radius: 4px;
            padding: 4px 6px;
        }}

        QLineEdit:focus {{
            border: 1px solid {c['accent']};
        }}

        /* Checkboxes had NO explicit styling at all before this -
           relying entirely on native OS rendering. That's exactly
           what made them turn invisible on macOS dark mode: a
           natively-drawn dark-mode indicator has no awareness this
           app's theme is light, so it can render with poor/no
           contrast against our own light row background. Every pixel
           is controlled explicitly here instead, so appearance is
           consistent regardless of the OS's own light/dark setting.
           Checked state uses a solid accent fill rather than a drawn
           checkmark glyph - avoids needing an image asset bundled
           with the app, and a solid color-fill difference is already
           clearly readable on its own. */
        QCheckBox {{
            color: {c['text']};
            spacing: 6px;
        }}

        QCheckBox::indicator {{
            width: 15px;
            height: 15px;
            border: 1.5px solid {c['text_muted']};
            border-radius: 3px;
            background: {c['bg_content']};
        }}

        QCheckBox::indicator:hover {{
            border: 1.5px solid {c['accent']};
        }}

        QCheckBox::indicator:checked {{
            background: {c['accent']};
            border: 1.5px solid {c['accent']};
        }}

        QCheckBox::indicator:disabled {{
            background: {c['bg_toolbar']};
            border: 1.5px solid {c['border']};
        }}

        /* A SEPARATE, genuinely different Qt selector from the
           QCheckBox rules above - this covers the tree's own NATIVE
           checkable-item indicator (ItemIsUserCheckable), used for
           the main per-row track-selection checkboxes in both the
           main tree and the Export dialog's inclusion tree. These are
           NOT QCheckBox widgets at all, so the rules above never
           touched them - confirmed directly this was the actual
           remaining gap (the KS/Midi-fy checkboxes ARE real QCheckBox
           widgets and were already covered; the main selection
           checkboxes specifically were not). Matches the same visual
           design as QCheckBox::indicator above for consistency. */
        QTreeView::indicator {{
            width: 15px;
            height: 15px;
            border: 1.5px solid {c['text_muted']};
            border-radius: 3px;
            background: {c['bg_content']};
        }}

        QTreeView::indicator:hover {{
            border: 1.5px solid {c['accent']};
        }}

        QTreeView::indicator:checked {{
            background: {c['accent']};
            border: 1.5px solid {c['accent']};
        }}

        QSpinBox {{
            background: {c['bg_content']};
            color: {c['text']};
            border: 1px solid {c['border']};
            border-radius: 4px;
            padding: 2px 6px;
        }}

        QSpinBox:focus {{
            border: 1px solid {c['accent']};
        }}

        QSpinBox::up-button, QSpinBox::down-button {{
            background: {c['bg_toolbar']};
            border-left: 1px solid {c['border']};
            width: 16px;
        }}

        QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
            background: {c['hover']};
        }}

        QComboBox {{
            background: {c['bg_content']};
            color: {c['text']};
            border: 1px solid {c['border']};
            border-radius: 4px;
            padding: 4px 6px;
        }}

        QComboBox:focus {{
            border: 1px solid {c['accent']};
        }}

        QComboBox::drop-down {{
            border-left: 1px solid {c['border']};
            width: 20px;
        }}

        QComboBox QAbstractItemView {{
            background: {c['bg_content']};
            color: {c['text']};
            border: 1px solid {c['border']};
            selection-background-color: {c['accent']};
            selection-color: {c['accent_text']};
        }}

        QListWidget {{
            background: {c['bg_content']};
            color: {c['text']};
            border: 1px solid {c['border']};
            border-radius: 4px;
            outline: none;
        }}

        QListWidget::item {{
            padding: 3px 4px;
        }}

        QListWidget::item:selected {{
            background: {c['accent']};
            color: {c['accent_text']};
        }}

        QListWidget::item:hover {{
            background: {c['hover']};
        }}

        QScrollArea {{
            background: transparent;
            border: none;
        }}

        QMessageBox {{
            background: {c['bg_app']};
            color: {c['text']};
        }}

        QScrollBar:vertical {{
            background: {c['bg_app']};
            border: none;
            width: 8px;
            margin: 0px;
        }}

        QScrollBar::handle:vertical {{
            background: {c['border']};
            border-radius: 5px;
            min-height: 24px;
        }}

        QScrollBar::handle:vertical:hover {{
            background: {c['text_muted']};
        }}

        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
    """
