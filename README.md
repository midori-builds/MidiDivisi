# MidiDivisi

A desktop tool for orchestral composers that imports MusicXML scores,
automatically separates notes by articulation/technique, and exports
clean, DAW-ready MIDI for sample library mapping — saving the manual
work of splitting tracks by hand before assigning them to patches in
your sampler.

Built for a notation → DAW workflow: write in Dorico/Sibelius/
MuseScore, export MusicXML, load it here, and get back MIDI already
separated into per-articulation tracks (staccato, pizzicato, tremolo,
mute, harmonics, and more) instead of one flat part per instrument.

This is not a notation editor, a DAW, or a MIDI sequencer — it's a
focused translator between the two.

## Status

Actively in development, built for personal use first. Not packaged
as a standalone app yet — run from source.

## Features

- MusicXML parsing with per-note and passage-level articulation
  detection (staccato, spiccato, tenuto, marcato, accents, trills,
  tremolo, pizzicato, mutes, harmonics — natural and artificial, with
  sounding-pitch correction — glissando, sul ponticello, sul tasto,
  col legno, flutter tongue, and more)
- Automatic sounding-pitch conversion for transposing instruments
- Velocity derived from written dynamics markings
- A non-destructive Session model: merge and split tracks or whole
  instruments at any time without losing the original data, rename
  freely, with full undo via split
- Export a whole score as one multi-track MIDI file, or one file per
  instrument, with per-track/per-instrument inclusion control
- A Settings dialog for customizing the keyword vocabulary used to
  detect free-text techniques (pizz., con sord., sul pont., etc.) and
  the velocity mapped to each dynamic marking — useful if your scores
  use different wording or languages than the built-in defaults

## Planned

Roughly in priority order:

- **Session save/load** — persist a session to disk so in-progress
  work survives closing the app
- **Sample library profiles** — per-library keyswitch/CC presets (EW,
  Spitfire, Orchestral Tools, etc.) so exported MIDI needs no manual
  patch-switching
- **Auto divisi/solo detection**
- **Auto condensing** — merging matching parts (e.g. four unison
  horns) into a single ensemble patch where appropriate
- Velocity humanizer, custom user-defined technique categories, and
  more — see `BACKLOG.md` for the full running list

## Requirements

- Python 3.10+
- [PyQt6](https://pypi.org/project/PyQt6/)
- [music21](https://pypi.org/project/music21/)
- [mido](https://pypi.org/project/mido/)

## Running it

Clone the repo, then set up a virtual environment:

```bash
# macOS / Linux
python3 -m venv venv
source venv/bin/activate

# Windows
python -m venv venv
venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the app:

```bash
python main.py
```

## License

GPLv3 — see `LICENSE`.
