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
    "bg_app": "#FAF6EE",
    "bg_toolbar": "#F1EBDD",
    "bg_content": "#FDFBF6",
    "border": "#DDD4C2",
    "text": "#2B2620",
    "text_muted": "#8A8073",
    "hover": "#EFE8D8",
    "accent": "#3584E4",
    "accent_text": "#FFFFFF",
}


def build_stylesheet():
    c = COLORS
    return f"""
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
    """
