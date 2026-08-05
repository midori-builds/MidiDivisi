"""
MIDI export logic.

Takes the note/chord groups produced by core.parser and writes them
out as MIDI. Built on music21's own Stream -> MIDI writer rather than
hand-rolling MIDI bytes, since we already have music21 Note/Chord
objects with correct offset (timing) and duration data from parsing.
"""

import copy
import os
import re

from music21 import instrument, stream

from mididivisi.core.parser import get_part_articulation_groups


def export_group_to_midi(notes, output_path):
    """Write a single articulation group (a list of Note/Chord objects)
    out as a one-track MIDI file, preserving each note's original
    offset (start time) and duration.

    notes objects are deep-copied before inserting into a fresh Stream,
    so this never mutates the original parsed score data.
    """
    s = stream.Stream()

    for n in notes:
        n_copy = copy.deepcopy(n)
        s.insert(n.offset, n_copy)

    s.write("midi", fp=output_path)


def _build_instrument_tracks(part, instrument_name):
    """Build one MIDI Part/track per articulation group found in a
    single music21 Part, named "<instrument> - <label>". Shared by
    both export modes below - a whole-score export just collects
    every part's tracks into one file, while per-instrument export
    writes each part's tracks into their own file.
    """
    groups = get_part_articulation_groups(part)
    tracks = []

    for label, notes in groups.items():
        track_name = f"{instrument_name} - {label}"

        track = stream.Part()

        # Setting .partName on the Part alone does NOT produce a MIDI
        # track_name meta event - music21's MIDI writer reads the name
        # from an Instrument object inserted into the stream instead.
        # Verified directly against exported bytes.
        track_instrument = instrument.Instrument()
        track_instrument.partName = track_name
        track.insert(0, track_instrument)

        for n in notes:
            n_copy = copy.deepcopy(n)
            track.insert(n.offset, n_copy)

        tracks.append(track)

    return tracks


def export_score_to_midi(score, output_path):
    """Walk every part in a parsed score, group notes by articulation
    (same grouping used for the console breakdown), and write the
    whole thing out as ONE multi-track MIDI file. Each
    (instrument, articulation) group becomes its own MIDI track,
    named "<instrument> - <label>" so it's recognizable once it lands
    in a DAW.

    Parts with no notes (e.g. tacet parts, or gaps like unpitched
    percussion that we don't parse yet) simply produce no tracks -
    nothing to export for them yet.
    """
    out_score = stream.Score()

    for part in score.parts:
        instrument_name = part.partName or "(unnamed part)"
        for track in _build_instrument_tracks(part, instrument_name):
            out_score.insert(0, track)

    out_score.write("midi", fp=output_path)


def _sanitize_filename(name):
    """Turn an instrument name into a safe filename: strip characters
    that are invalid (or awkward) on Windows/Mac filesystems.
    """
    # Replace anything that isn't alphanumeric, space, dash, or
    # underscore with an underscore, then collapse repeated
    # whitespace.
    safe = re.sub(r"[^\w\s-]", "_", name)
    safe = re.sub(r"\s+", " ", safe).strip()
    return safe or "unnamed_instrument"


def export_score_to_midi_per_instrument(score, output_dir):
    """Same grouping as export_score_to_midi, but writes ONE MIDI file
    per instrument/part into output_dir, instead of combining
    everything into a single file. Each file still contains multiple
    tracks internally - one per articulation group for that
    instrument.

    Parts with no notes are skipped entirely (no empty file written).
    Instrument names that repeat (e.g. grand-staff duplicates like
    Harp appearing as two separate parts) get a numeric suffix so
    files don't silently overwrite each other.

    Returns the list of file paths actually written.
    """
    written_paths = []
    used_filenames = {}

    for part in score.parts:
        instrument_name = part.partName or "(unnamed part)"
        tracks = _build_instrument_tracks(part, instrument_name)

        if not tracks:
            continue  # nothing to export for this part

        base_filename = _sanitize_filename(instrument_name)

        # Disambiguate repeated instrument names (e.g. two "Harp"
        # parts from a grand staff) so we don't overwrite files.
        count = used_filenames.get(base_filename, 0)
        used_filenames[base_filename] = count + 1
        filename = base_filename if count == 0 else f"{base_filename} ({count + 1})"

        output_path = os.path.join(output_dir, f"{filename}.mid")

        out_score = stream.Score()
        for track in tracks:
            out_score.insert(0, track)
        out_score.write("midi", fp=output_path)

        written_paths.append(output_path)

    return written_paths
