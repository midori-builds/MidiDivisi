"""
Settings/config data model.

Unlike Session (deliberately in-memory-only, per-score), this IS
persisted to disk - it's configuration, not per-score data, so it
should survive between runs of the app. Stored as a small JSON file
under the user's home directory.

Currently holds one thing: the keyword mapping used to detect
passage-level techniques (pizzicato/arco, mute/senza sord.) from free-
text directions in the score. This was previously a small hardcoded
English vocabulary in parser.py - a real functional limitation for
anyone whose scores use different wording (other languages,
abbreviations we didn't anticipate, house-style conventions). Making
it user-editable is the whole point of this first Settings page.

More categories (dynamics/velocity mapping, sample library profiles,
CC11 curve settings, etc.) are planned - see BACKLOG.md - and would
extend this same Settings class with new fields, saved/loaded the
same way.
"""

import json
import os

SETTINGS_DIR = os.path.expanduser("~/.mididivisi")
SETTINGS_PATH = os.path.join(SETTINGS_DIR, "settings.json")

# Human-readable label for each keyword-mapping category, in display
# order. The dict key is what's actually stored/matched against in
# parser.py; the label is only for the Settings UI.
KEYWORD_CATEGORY_LABELS = {
    "pizzicato_on": "Pizzicato (start)",
    "pizzicato_off": "Pizzicato end (arco)",
    "mute_on": "Mute (start)",
    "mute_off": "Mute end (senza sord.)",
}

DEFAULT_KEYWORD_MAPPING = {
    "pizzicato_on": ["pizz", "pizzicato"],
    "pizzicato_off": ["arco"],
    "mute_on": ["mute", "muted", "con sord", "con sordino", "sord"],
    "mute_off": ["senza sord", "senza sordino", "open", "unmuted"],
}


class Settings:
    """Holds current settings values and knows how to load/save
    itself. Meant to be used as a single shared instance (see
    `settings` at the bottom of this module) so parser.py and any
    Settings UI are always looking at the same live data.
    """

    def __init__(self):
        # Deep-copy the defaults so mutating self.keyword_mapping
        # never touches the DEFAULT_KEYWORD_MAPPING constant itself.
        self.keyword_mapping = {k: list(v) for k, v in DEFAULT_KEYWORD_MAPPING.items()}
        self.load()

    def load(self):
        """Load settings from disk, if a settings file exists. Missing
        categories in the file fall back to defaults rather than
        disappearing (so adding a new category later doesn't break
        existing users' saved files), and any read/parse failure is
        treated the same as "no settings file yet" - falls back to
        defaults silently rather than crashing the app over a
        corrupted config file.
        """
        if not os.path.exists(SETTINGS_PATH):
            return

        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return

        loaded_mapping = data.get("keyword_mapping", {})
        for category, words in loaded_mapping.items():
            self.keyword_mapping[category] = list(words)

    def save(self):
        os.makedirs(SETTINGS_DIR, exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump({"keyword_mapping": self.keyword_mapping}, f, indent=2)

    def get_keyword_set(self, category):
        """Return the current word set for a category, normalized
        (lowercase, stripped) the same way parser.py's matching logic
        expects. Empty set if the category doesn't exist for some
        reason, rather than raising.
        """
        return {w.strip().lower() for w in self.keyword_mapping.get(category, [])}

    def reset_category_to_default(self, category):
        self.keyword_mapping[category] = list(DEFAULT_KEYWORD_MAPPING.get(category, []))


# Shared singleton instance - import THIS, not the class, from
# anywhere that needs current settings (parser.py, the Settings UI).
settings = Settings()
