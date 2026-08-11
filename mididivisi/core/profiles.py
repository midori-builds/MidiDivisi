"""
Profile/Collection data model.

Two levels:
  - Collection: a named group of Profiles, typically one per sample
    library (e.g. "EW Hollywood Winds"). Mandatory owner of every
    Profile - no orphan profiles, matching the same "no floating
    tree nodes" rule Session already follows (a Group never exists
    without an owning Instrument).
  - Profile: one instrument's worth of library-specific setup (e.g.
    "Violin I" within "EW Hollywood Winds"). Holds an ordered list of
    InventoryItems - the library's OWN articulation bucket names
    (e.g. "Short", "Long", "Pizzicato"), each with:
      - matched_labels: which of OUR internally-detected articulation
        labels (Staccato, Sustain+Accent, Tremolo-M3, etc.) feed into
        this bucket
      - keyswitch_note: a MIDI note number that triggers this bucket
        in the target library, or None (keyswitching is opt-in per
        item, and per-instrument at the Session level - see
        Instrument.keyswitch_enabled in session.py)

Persisted separately from Settings (own file, profiles.json) rather
than folded into Settings - profiles are a growing, actively-worked-in
library the user builds out over time, not small global config set
once and forgotten, so they get their own persistence and (planned)
their own dedicated Profile Manager UI rather than living in the
Settings dialog.

Collection/Profile export-import (portability - sharing/backing up a
library's worth of profiles, or a single profile, independent of the
full profiles.json) is plain JSON, same shape as what's stored
on disk - no binary data needs to travel with it, unlike Session
(which bundles the original score).
"""

import json
import os
import uuid

from mididivisi.core.settings import PROJECT_ROOT

PROFILES_PATH = os.path.join(PROJECT_ROOT, "profiles.json")


class InventoryItem:
    """One bucket in a library's articulation inventory (e.g. "Short").
    `name` is the library's own name for this bucket - entirely user-
    defined text, not pulled from our internal vocabulary. That
    internal vocabulary is what `matched_labels` references instead.
    """

    def __init__(self, name):
        self.id = str(uuid.uuid4())
        self.name = name  # mutable, user-editable
        self.matched_labels = []  # list of our internal articulation label strings
        self.keyswitch_note = None  # MIDI note number, or None (default)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "matched_labels": list(self.matched_labels),
            "keyswitch_note": self.keyswitch_note,
        }

    @classmethod
    def from_dict(cls, data):
        item = cls(data["name"])
        item.id = data["id"]
        item.matched_labels = list(data.get("matched_labels", []))
        item.keyswitch_note = data.get("keyswitch_note")
        return item

    def __repr__(self):
        return f"InventoryItem(name={self.name!r}, matched={len(self.matched_labels)}, ks={self.keyswitch_note})"


class Profile:
    """One instrument's worth of library-specific setup. `name` is
    typically the instrument's name (e.g. "Violin I"), but is free
    text - nothing enforces it matching an actual instrument.
    """

    def __init__(self, name):
        self.id = str(uuid.uuid4())
        self.name = name  # mutable, user-editable
        self.inventory = []  # list of InventoryItem, in display order

    @property
    def has_keyswitches(self):
        return any(item.keyswitch_note is not None for item in self.inventory)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "inventory": [item.to_dict() for item in self.inventory],
        }

    @classmethod
    def from_dict(cls, data):
        profile = cls(data["name"])
        profile.id = data["id"]
        profile.inventory = [InventoryItem.from_dict(d) for d in data.get("inventory", [])]
        return profile

    def __repr__(self):
        return f"Profile(name={self.name!r}, inventory={len(self.inventory)} item(s))"


class Collection:
    """A named group of Profiles, mandatory owner - Profiles never
    exist without a Collection (see module docstring for why).
    """

    def __init__(self, name):
        self.id = str(uuid.uuid4())
        self.name = name  # mutable, user-editable
        self.profiles = []  # list of Profile

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "profiles": [p.to_dict() for p in self.profiles],
        }

    @classmethod
    def from_dict(cls, data):
        collection = cls(data["name"])
        collection.id = data["id"]
        collection.profiles = [Profile.from_dict(d) for d in data.get("profiles", [])]
        return collection

    def __repr__(self):
        return f"Collection(name={self.name!r}, profiles={len(self.profiles)})"


class ProfileLibrary:
    """Holds every Collection and knows how to load/save itself to
    disk. Meant to be used as a single shared instance (see `library`
    at the bottom of this module), same pattern as Settings.
    """

    def __init__(self):
        self.collections = []
        self.load()

    def load(self):
        if not os.path.exists(PROFILES_PATH):
            return
        try:
            with open(PROFILES_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return
        self.collections = [Collection.from_dict(d) for d in data.get("collections", [])]

    def save(self):
        with open(PROFILES_PATH, "w", encoding="utf-8") as f:
            json.dump(
                {"collections": [c.to_dict() for c in self.collections]}, f, indent=2
            )

    def add_collection(self, name):
        collection = Collection(name)
        self.collections.append(collection)
        self.save()
        return collection

    def remove_collection(self, collection_id):
        self.collections = [c for c in self.collections if c.id != collection_id]
        self.save()

    def find_profile(self, profile_id):
        """Find a Profile by id across every Collection. Returns
        (collection, profile) or (None, None) if not found.
        """
        for collection in self.collections:
            for profile in collection.profiles:
                if profile.id == profile_id:
                    return collection, profile
        return None, None


def export_collection(collection, output_path):
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"collection": collection.to_dict()}, f, indent=2)


def import_collection(input_path):
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return Collection.from_dict(data["collection"])


def export_profile(profile, output_path):
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"profile": profile.to_dict()}, f, indent=2)


def import_profile(input_path):
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return Profile.from_dict(data["profile"])


# Shared singleton instance - import THIS, not the class.
library = ProfileLibrary()
