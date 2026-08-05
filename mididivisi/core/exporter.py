"""
MIDI export logic.

Takes the note/chord groups produced by core.parser and writes them
out as MIDI. Built on music21's own Stream -> MIDI writer rather than
hand-rolling MIDI bytes, since we already have music21 Note/Chord
objects with correct offset (timing) and duration data from parsing.
"""

import copy

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
        groups = get_part_articulation_groups(part)

        for label, notes in groups.items():
            track_name = f"{instrument_name} - {label}"

            track = stream.Part()

            # Setting .partName on the Part alone does NOT produce a
            # MIDI track_name meta event - music21's MIDI writer reads
            # the name from an Instrument object inserted into the
            # stream instead. Verified directly against exported bytes.
            track_instrument = instrument.Instrument()
            track_instrument.partName = track_name
            track.insert(0, track_instrument)

            for n in notes:
                n_copy = copy.deepcopy(n)
                track.insert(n.offset, n_copy)

            out_score.insert(0, track)

    out_score.write("midi", fp=output_path)
