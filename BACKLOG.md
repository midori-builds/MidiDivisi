# MidiDivisi Backlog

Things still to work on. For what's already been built and why -
design history, debugging lessons, verified findings - see
`DEVLOG.md`. Nothing here is urgent; this exists so none of it gets
lost between sessions.

## Roadmap

The three original priorities (Profiles → Auto Divisi/Solo →
Condensing) are now Profiles (functionally complete) and Divisi/Solo
(done) behind us. **Auto Condensing is the one big feature left from
that original list, and it's the next natural thing to build** - see
its own section below for the full design (already substantially
fleshed out, not starting from scratch).

Also actively being built: **midi-fy** (`core/midifi.py`) is the
shared foundation for turning notated techniques into real MIDI
events. Tremolo (single-note), trills (basic oscillation), and
tremolo spanner are all done - see "Midi-fy features" below for
what's left (arpeggio, glissando, legato, and the shared instrument/
interval classification system trill and tremolo spanner both still
need).

## Auto Condensing / Score Condensing

Not started - design substantially fleshed out first, though (see
DEVLOG.md for the full reasoning behind each decision below).

**Design, agreed:**
- User selects 2+ whole instruments and clicks "Condense," opening a
  Condense Options dialog.
- Breadth is fixed, not a threshold: a moment only counts as condensed
  if ALL selected instruments agree (no partial-subset matching).
- "Notes in common" = exact pitch AND exact duration match at the same
  offset across every selected instrument.
- "Minimum Count" = minimum CONSECUTIVE run length (filters out a
  single coincidental unison note in an otherwise-independent
  passage).
- Bar range filtering (e.g. "1-5, 9-12, 18", blank = whole track) -
  confirmed technically easy (`note.measureNumber` is directly
  available at parse time); the only new work is ordinary string-range
  parsing.
- Condensed result becomes a new track, restricted from being merged
  with anything else.
- Original tracks are NOT destructively edited - notes belonging to a
  condensed stretch get flagged for export-exclusion instead, keeping
  the note data intact.
- Re-editing or removing a condensed track should fully recompute from
  scratch each time (same "rebuild clean, never patch" pattern used
  for Profiles and midi-fy).

**Still open / not yet decided:**
- Exact mechanism for per-note (or per-bar-range) export exclusion on
  the original tracks - `Group.included`/`Track` currently only
  support whole-group inclusion toggling; this needs genuinely new
  data-model capability.
- What happens visually/structurally when a condensed track's source
  instruments later get merged, split, or removed.
- Whether condensed tracks need their own distinct visual treatment in
  the tree (e.g. an indicator similar to the "M" merge marker).

## Midi-fy features

`core/midifi.py` is the shared foundation for turning notated
techniques into real MIDI events. Different features have turned out
to need genuinely different CONFIG SCOPES - tremolo's threshold is
session-wide, trill/tremolo-spanner classification will be per-
instrument, glissando/legato look like they'll want per-profile -
worth staying alert to that rather than forcing everything into one
shape.

**Done** (full implementation history and verification detail for
each in DEVLOG.md):
- Tremolo (single-note) - realizes below-threshold flag counts into
  discrete repeated notes.
- Trills (basic oscillation) - per-row toggle, instant, rate
  configurable per-project. Stress-tested against 15 real trills
  across 4 instruments in `Woods.musicxml`, no bugs found - and in
  the process, disproved a previously-listed gap: accented trills
  already correctly get the accent velocity boost for free (measured
  110 vs. 96), since realization deep-copies the already-fully-
  processed original note.
- Tremolo spanner (measured 2-note/chord tremolo) - same toggle
  mechanism as trill, but with a real generalization: the off state
  is ALSO a transformation here (collapses to one sustained note/
  chord for a dedicated patch), not a no-op. A real correctness bug
  was found and fixed during this work (exporting once while toggled
  on was silently corrupting the same passage's ability to be
  correctly toggled again afterward) - see DEVLOG.md for the full
  story.

**Not yet built:**
- **Instrument/interval classification system** - needed by BOTH
  trill (oscillation vs. tremolo-style, e.g. timpani) and tremolo
  spanner (some owned libraries have dedicated 3rd-interval trill
  patches that shouldn't be midi-fied) - the same system, not two
  separate ones. Lives in the Midi-fy window per-project, with a
  separate global-defaults editor + restore-to-defaults action - full
  design already agreed (see DEVLOG.md). Genuinely narrow impact for
  trill specifically (the current oscillation default is already
  correct for the vast majority of real usage - strings, most
  woodwinds/brass); tremolo spanner already has the interval data
  this needs sitting in its label, ready for whenever this gets
  built.
- Trill speed shape beyond linear (curves, custom) and a humanizer -
  both deliberately hardcoded/off for the MVP, but the generation
  function already takes them as real parameters with hardcoded
  defaults, so this should be wiring, not restructuring, when
  tackled.
- **Arpeggio** - a chord marked `<arpeggiate>`. No sample library has
  an "arpeggio patch" - needs to become real staggered note-on events.
  Direction-aware (up/down/non-arpeggio) data is already retrievable
  via `ArpeggioMarkSpanner`/`ArpeggioMark.type`, just not used yet.
- **Glissando** - currently labeled/separated into its own track
  (some harp libraries have a dedicated gliss patch), but for
  libraries that don't, this needs the same "expand into real notes"
  treatment. Real open design question from a recent conversation:
  the on/off decision here likely belongs on the PROFILE (per-library),
  not the session, unlike tremolo - since whether to midi-fy depends
  on the target library, not the piece. If so, the realization itself
  would need to be scoped to just that profile's tracks on reapply,
  not a full session rebuild - not yet designed.
- **Legato** - discussed at length, not designed to completion yet.
  Real open pieces:
  - Toggle likely lives per-articulation on a Profile's inventory
    item, not session-wide (same reasoning as glissando above).
  - Enabling it should extend adjacent (non-chord) notes' durations to
    interlock until a rest - and the resulting notes should
    auto-merge into their base articulation bucket, same
    "Merge Midi-fy" pattern already built for tremolo, not stay in
    their own track.
  - Divisi interaction: confirmed a REAL fix was needed and is now
    done (divisi is a separate Instrument, so it can never get
    silently flattened into a keyswitch track just because a profile's
    keyword-matching happens to match it) - but legato's own
    interaction with divisi/keyswitch specifics hasn't been re-checked
    since.
  - Polyphonic material (a monophonic instrument with an occasional
    chord in the middle of a legato passage) - leaning toward
    "refuse cleanly, don't guess" for a first version (consistent with
    how divisi/harmonics both handle their own ambiguous-shape cases),
    with "skip just the chord and its immediate neighbors, legato the
    rest" as a possible middle-ground refinement - not decided.
- **Caveat for whoever builds any of these**: music21's importer
  silently defaults to `numberOfMarks = 3` if a `<tremolo>` element is
  malformed or missing its count entirely - an observed "3" could
  occasionally be missing data masquerading as a genuine 3-flag
  tremolo. Not currently guarded against.

## Notation preview - still pending pieces

Crude v1 (per-instrument Preview button, real extracted notation via
Verovio, zoom/fit, working text labels) is done. Not yet built:

- Opt-in per-window highlighting scoped to a side panel mirroring the
  tree, multi-select, a small fixed color palette for it (~4-6 colors)
  - full original design exists, just not built.
- "Preview whole score" - same mechanism, scoped to every instrument.
- Grand-staff instruments (Harp, Piano, etc.) can't be split per
  occurrence in preview yet - both "occurrences" currently show the
  same combined notation, since the raw MusicXML often has only one
  `<part>` for what music21 splits into two.
- Merged (multi-identity) instruments only preview their first
  identity, not a combined view.
- New dependency `verovio` isn't reflected in a requirements.txt yet
  (none exists in the dev environment this was built in).

## Divisi - open items

- **Dorico's native Divisi feature isn't detected** (only manually-
  typed `div.`/`unis.` text works) - confirmed this is a genuine
  Dorico export quirk on the source side, not a bug here, and the
  user is investigating further on their own end. Real design tension
  still unresolved: for STRING instruments specifically, genuine
  multi-voice content arguably implies divisi inherently (a single
  player can't produce two independent lines), which could allow
  dropping the marker requirement for that instrument family - but
  needs some notion of "which instruments are monophonic" that doesn't
  exist yet, and risks misreading legitimate multi-voice writing on
  keyboard/harp instruments if applied too broadly. Revisit if this
  comes up again in practice.
- Cosmetic: a genuinely-empty duplicate instrument row (from the
  Dorico quirk above) still clutters the tree. Low priority, tied to
  the same unresolved investigation.
- Wind/brass "a3"/"a4" exploding is a deliberately DIFFERENT, unbuilt
  problem from string divisi (an identity-reconciliation problem -
  reconciling with specific named players like Horn 1/2 - not a
  note-splitting one). Loosely the inverse of the grand-staff merge
  work; worth designing alongside that if ever tackled.

## Profiles - smaller open items

- Auto-assigning profiles to instruments (e.g. guessing from
  instrument name) - explicitly deferred as "a different task."
- A toggle-all-KS convenience button.
- Profile/Collection JSON import doesn't validate or de-duplicate
  keyword-matching conflicts the way the interactive "Add" button now
  does.
- No defined behavior if a Collection/Profile currently assigned to an
  instrument gets deleted in the Profile Manager while that session is
  open (doesn't crash, but becomes an orphaned, invisible assignment).
- Per-library note ranges - not yet part of the Profile/InventoryItem
  data model at all.

## UI polish

- Tree collapse/expand state is lost on every merge/split/rename,
  since `refresh_tree()` rebuilds the whole tree from scratch. Scroll
  position already uses a capture/restore pattern around the rebuild
  that this could likely reuse.
- Manual instrument/track reordering (drag-and-drop or up/down
  controls) - now that merge/split correctly preserve position rather
  than scrambling it, manual reordering is a natural next feature, not
  just a bug fix.
- Per-instrument export filename prefix (opt-in checkbox in the export
  dialog, reusing the existing "File name" field as a prefix).
- Minor: when a merged group/instrument is later split back apart, the
  results land in the correct position range, but their exact order
  within that range reflects click-order at merge time, not original
  pre-merge order. Cosmetic only.
- A bronze/dark "luxury" orchestral theme variant was discussed with a
  starter palette proposed, not built (would be a second palette dict
  + a switch, not a rewrite).

## Known parsing/data gaps

- **Exported `note_on` count doesn't match parsed note/chord object
  count, gap unexplained** - found while testing the trill toggle
  mechanism (see "Midi-fy features" above), confirmed
  unrelated to that work specifically (the same gap exists via the
  pre-existing code path too, not something the toggle introduced).
  For `String_Test_Piece.musicxml`: 293 parsed note/chord objects,
  but 311 actual `note_on` events in the exported MIDI. Some of that
  gap is expected and not a bug (a single Chord object legitimately
  produces multiple `note_on` events, one per pitch), but a full
  pitch-level count came to 318, not 311 - a 7-note gap still
  unaccounted for. Checked one candidate explanation (duplicate
  pitches within a single chord) and ruled it out directly. Not
  chased down further since it was out of scope for what was being
  tested - worth a dedicated look on its own.
- Unpitched percussion is not parsed at all - `Unpitched` objects
  aren't `Note`/`Chord`, silently skipped. Needs its own detection
  path (no pitch, only instrument/sound identity) - no plan yet.
- Horns 3/4 (Sibelius export) show zero notes despite the composer
  confirming they're not tacet. Never diagnosed - suspected Sibelius
  export quirk, unconfirmed. Low priority but a real correctness gap.
- Multi-voice note ordering is assumed, not guaranteed - the
  state-timeline logic (pizzicato/mute/dynamics tracking) assumes
  notes come out of `part.flatten().notes` in offset order. Held true
  for every test file so far; worth a dedicated stress-test file for
  dense multi-voice writing.
- Keyword vocabulary is still a fairly small, English-only starter set
  (now user-editable via Settings, but the built-in coverage itself is
  limited) - will likely need to grow for other languages/composers.
- Filename sanitization: instrument names with commas (e.g.
  "Bassoons 1, 2") become "Bassoons 1_ 2.mid" in per-instrument
  export. Cosmetic, low priority.
- Natural harmonics - whether the written pitch represents the touched
  node or the already-correct sounding pitch is genuinely ambiguous by
  MusicXML convention and composer-dependent. Currently exported as
  literal written pitch, unverified whether that's correct. Worth
  settling once there's a real test case to check against.
- Cross-notation-software testing for the sounding-pitch conversion -
  confirmed correct for Dorico's "Concert Pitch" export, not yet
  tested against Sibelius or MuseScore's equivalent. Real risk of
  double-transposition if a program bakes sounding pitch into
  `<pitch>` while still declaring a non-zero `<transpose>`.

## Dynamics / tempo

- Hairpins (crescendo/diminuendo) are NOT interpolated - a note mid-
  hairpin just keeps the last named dynamic's velocity. Deferred
  because spanner endpoints proved fragile to resolve reliably.
- CC11 (Expression) continuous dynamics curves - a separate, larger
  feature from velocity, needs its own design (which CC number, curve
  shape, genuine interpolation over sustained notes). Belongs
  downstream of both Session and Profiles.
- Velocity humanizer - a random multiplier on top of dynamics-mapped
  velocity, off by default. Real open questions: gaussian vs. uniform
  distribution, percentage vs. absolute range (behaves very
  differently at `ppp` vs. `ff`), deterministic seeding so re-exports
  don't reshuffle humanization, and applying at export time (not
  baked into parse-time note data) so toggling doesn't need a reload.
- Gradual tempo changes (accelerando/ritardando) are not recognized -
  a deliberate scope decision (same reasoning as hairpins - a
  continuous change with no single target value is fragile to
  interpolate and often not well-defined in the source anyway), not a
  bug. "A Tempo" is a real exception and already works, since it
  typically carries an explicit tempo hint. Revisit alongside hairpins
  if ever tackled, as one shared "continuous change" feature rather
  than two ad hoc ones.

## Settings dialog - planned future pages

- CC11 dynamics-curve mapping (downstream of Profiles).
- Realization-strategy defaults for tremolo/arpeggio/glissando
  (global default, before profile/per-track overrides).
- Velocity humanizer settings (enable checkbox, multiplier scale).
- Merge-conflict "remember my decision" preference - the storage
  location was decided early on, but the merge-conflict dialog itself
  (asking how to resolve overlapping notes from a merge) was never
  built, so this setting currently has nothing to control.

## Custom keyword categories

Letting a user define their own technique (beyond the built-in
pizzicato/mute/flutter/sul pont/sul tasto/col legno) and get it
separated into its own track. Not urgent. Two real implications when
tackled:
- `STATE_KEYWORD_CATEGORIES` in `parser.py` is currently a hardcoded
  Python list - true user-defined categories means this becomes
  data-driven from Settings instead, a real structural change.
- Start/end keyword pairs should be presented as one obviously-paired
  UI unit rather than two independent rows - the current Keyword
  Mapping UI already has this weakness for the built-in categories too
  (worth revisiting for all of them at once, not just new custom ones).

## Not yet scoped / farther out

- Packaging/distribution as a standalone app (PyInstaller/Nuitka)
  rather than "run from source in a venv" - relevant once this isn't
  just for personal use.
- Batch processing - exporting multiple MusicXML files in one pass.
- Keyswitch note-on collision: if two different matched groups have
  notes at the exact same offset (a genuinely simultaneous multi-
  articulation moment), the inserted keyswitch note-on could collide
  with real notes from the other group. Deliberately accepted as a
  rare edge case; revisit only if it actually comes up.
- MIDI CC-based keyswitching (as opposed to note-based) - not built,
  only note-on keyswitches exist right now.
