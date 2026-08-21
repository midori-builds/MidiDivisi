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
- Auto divisi/solo detection — divisi passages (chord-based and
  voice-based) and solo passages are recognized and split into their
  own separate instruments automatically
- **Sample library profiles** — define per-library instrument
  inventories with keyswitch mapping via the Profile Manager, then
  apply a profile to any instrument; export automatically flattens
  matched articulations into one keyswitched track
- **Midi-fy** — turns notated ornaments that most sample libraries
  don't have a dedicated patch for into real, DAW-ready MIDI:
  - **Trills** — realized into alternating notes, tempo-relative rate
    (toggle per row in the tree)
  - **Measured tremolo (2-note/chord spanner)** — realized into
    alternating notes when toggled on, or collapsed into one
    sustained note/chord for a dedicated tremolo/roll patch when off
    (toggle per row in the tree)
  - **Arpeggios** — realized into a staggered roll (tempo-relative
    delay per note, correct direction up/down/explicit, correct
    across grand-staff instruments), controlled by one global setting
    since no sample library has a dedicated arpeggio patch
  - **Single-note tremolo** — realized into discrete repeated notes
    below a configurable flag threshold, left as one sustained note
    above it for a dedicated tremolo patch
  - All midi-fy realization is computed non-destructively wherever
    possible (trill, tremolo spanner, arpeggio) — toggling never
    loses the original notated data, and settings apply live without
    needing to reload the file
- A non-destructive Session model: merge and split tracks or whole
  instruments at any time without losing the original data (including
  auto-merge for accent variants and midi-fy-tagged variants), rename
  freely, with full undo via split
- **Session save/load** — persist a session to disk (`.mididivisi`
  files) so in-progress track/profile/rename work survives closing
  the app
- **Notation preview** — view the actual extracted notation for any
  instrument's track before exporting, to sanity-check what got
  separated
- Export a whole score as one multi-track MIDI file, or one file per
  instrument, with per-track/per-instrument inclusion control
- A Settings dialog for customizing the keyword vocabulary used to
  detect free-text techniques (pizz., con sord., sul pont., etc.) and
  the velocity mapped to each dynamic marking — useful if your scores
  use different wording or languages than the built-in defaults

## Planned

Roughly in priority order — see `BACKLOG.md` for the full running
list with implementation detail, and `DEVLOG.md` for the history of
what's already been built and why:

- **Auto condensing** — merging matching parts (e.g. four unison
  horns) into a single ensemble patch where appropriate
- **Glissando and legato midi-fy** — realized into real note events,
  same shape as trill/tremolo/arpeggio
- **Instrument/interval classification** — per-instrument defaults for
  which trills/tremolo-spanner intervals should be midi-fied vs. left
  for a dedicated library patch (e.g. timpani rolls, 3rd-interval
  trill patches)
- Velocity humanizer, custom user-defined technique categories, and
  more

## Requirements

- Python 3.10+
- [PyQt6](https://pypi.org/project/PyQt6/)
- [music21](https://pypi.org/project/music21/)
- [mido](https://pypi.org/project/mido/)
- [verovio](https://pypi.org/project/verovio/) — notation rendering for the Preview feature

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
