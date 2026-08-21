# MidiDivisi Development Log

Chronological record of what's been built, why, and what was learned
along the way - design decisions, verified findings, debugging
lessons, and the reasoning behind choices that aren't obvious just
from reading the code. For what's still left to do, see
`BACKLOG.md` - that file stays a scannable TODO list; this one is the
"why does it work this way" reference.

## Roadmap priority: Profiles → Auto Divisi/Solo → Auto Condensing

The three big features discussed as personal-workflow priorities, in
the order agreed on, with reasoning:

1. **Profiles - IN PROGRESS, functionally complete for a single
   session, but with one significant cross-feature gap found on
   review (see below).** This is what actually closes the loop the
   whole app exists for. Parsing/Session/export already produce
   clean, correctly-separated tracks; Profiles is what removes the
   remaining manual step of assigning each track to the right
   patch/keyswitch in the DAW.
   - **Done and tested**: full data model (`core/profiles.py` -
     Collection/Profile/InventoryItem, JSON persistence, Collection-
     and Profile-level export/import); `Session.apply_profile()`
     (regroups an instrument's tracks per the profile's inventory,
     structurally guaranteed to never touch instrument-merge state,
     and `merge_groups` now correctly propagates `profile_item` onto
     merge results, order-independently, so manually merging an
     unmatched articulation into a matched one genuinely resolves the
     gap both visually and at export - not just cosmetically);
     standalone Profile Manager window (build/edit Collections and
     Profiles - inventory add/remove/rename, keyword matching with
     Auto-Add and a conflict warning before silently reassigning a
     keyword, profile-level keyswitch toggle with a real note-name
     picker, not a raw MIDI number); per-instrument "Select Profile"
     picker dialog (empty-inventory profiles shown-but-disabled with
     a tooltip, Clear Assignment, shortcut into the Manager); main
     tree gained Profile and KS columns per instrument, KS checkbox
     only shown when the assigned profile actually has a keyswitch
     defined; unmatched articulations are highlighted blue in the
     tree with a "Missing in profile" tooltip; cross-window auto-
     refresh (editing a profile in the separate Manager window
     immediately updates the main tree); real KEYSWITCH EXPORT -
     `exporter.py` flattens a keyswitch-enabled instrument's MATCHED
     groups into one track with keyswitch note-ons inserted at every
     bucket transition, while UNMATCHED groups correctly export as
     their own separate track (folding them into the flattened track
     with no keyswitch cue would be actively wrong, not just
     unhelpful - confirmed and fixed).
   - **~~Session save/load has no idea Profiles exist~~ — DONE.**
     `session_file.py` now saves `(profile_id, keyswitch_enabled)` per
     instrument and `profile_item_id` per group, re-resolving both
     against the LIVE `ProfileLibrary` on load (by id) rather than
     embedding a frozen snapshot - a Profile is a persistent, edited-
     over-time resource, so a reload correctly reflects its CURRENT
     state, same philosophy already used for natural-key track
     resolution. Verified with the exact round trip that originally
     confirmed the gap (profile, keyswitch toggle, and profile_item
     all correctly survive save+reload), plus both graceful-
     degradation paths: a profile deleted from the library between
     save and load (clears assignment, one clear warning, no crash),
     and an inventory item deleted from an otherwise-still-existing
     profile (clears just that group's profile_item, profile itself
     stays correctly resolved). Confirmed zero regression for sessions
     that don't use Profiles at all.
   - Smaller, still open: auto-assigning profiles to instruments
     (explicitly deferred as "a different task" during design); a
     toggle-all-KS convenience button (mentioned as a maybe-later);
     Profile/Collection JSON import doesn't validate or de-duplicate
     keyword-matching conflicts the way the UI's Add button now does
     (flagged during the "how does keyword matching work" discussion,
     never fixed - only the UI path got the warning); what should
     happen if a Collection/Profile currently assigned to an
     instrument gets deleted in the Profile Manager while that session
     is open (currently: nothing crashes, since Python keeps the
     object alive via the instrument's own reference, but it becomes
     an orphaned assignment invisible in the Manager - not considered
     yet).
   - Adjacent/downstream, not really Profiles itself: per-library note
     ranges (not in the data model at all yet); realization-strategy
     defaults (tremolo/arpeggio/glissando) tied to profiles - separate
     unbuilt feature; CC11 dynamics-curve mapping - separate unbuilt,
     downstream feature.
   - Confirmed intentional, NOT a gap: splitting a matched group
     produces sub-groups with `profile_item = None` (a single
     InventoryItem can't meaningfully cover only part of a split) -
     reasoned through explicitly and consistent with how the highlight
     +export logic already treats "no profile_item" everywhere else.
2. **Auto Divisi/Solo** second - more tractable than it looks, because
   "solo"/"div."/"a2"/"unis." are passage-level text directions, the
   same shape of problem our keyword-timeline system (pizz/arco, sul
   pont/ord., etc.) already solves. Likely an extension of existing
   infrastructure, not a new subsystem. Also more valuable once
   Profiles exists, since correctly identifying a solo passage
   matters more when there's a solo patch to route it to
   automatically.
3. **Auto Condensing** last - genuinely the hardest of the three. Not
   reading an explicit cue in the score like the other two; requires
   comparing multiple tracks' actual note content over a sliding
   window and judging "coincidental overlap vs. intentional unison" -
   exactly the ambiguity flagged early on (one note matching in an
   otherwise-independent running passage shouldn't trigger merging).
   Wants the app more battle-tested first.

**~~Session save/load~~ — DONE.** Built and tested: `.mididivisi` zip
bundling session structure (keyed by stable natural keys, not the
random UUIDs that change every parse), a copy of the original score,
and a Settings snapshot (with a differ-detection prompt on load - use
saved settings or current). File menu gained Open Session/Save
Session/Save Session As/Close File; drag-and-drop onto the whole
window for both MusicXML and session files.

## Notation preview (crude v1 DONE - fuller design still pending)

**Crude v1 built and tested, pulled ahead of schedule** - motivation
became concrete rather than hypothetical: diagnosing the real Dorico
divisi export issue (see "Auto Divisi / Solo detection" above)
required manually reading raw XML and cross-referencing music21
internals, exactly the kind of thing this feature exists to make
fast/visual instead.

- **Per-instrument "Preview" button** in the main tree (new column) -
  extracts that instrument's REAL `<part>` directly from the original
  MusicXML file (not reconstructed from our own flat Track/Group note
  data - confirmed this matters: our data has no measure/voice/
  beaming structure at all, so a from-scratch render would mean
  solving most of what makes notation software hard in the first
  place) and renders it via Verovio (`pip install verovio` - confirmed
  a real, current, actively maintained library before relying on it,
  same as originally researched) into a plain, non-modal window with
  basic page navigation.
- **Deliberately minimal for v1, per design discussion**: no
  highlighting, no side panel, no multi-select - just "show me the
  real notation." Non-modal and independently spawnable (clicking
  Preview on several instruments opens several separate windows), so
  the core "compare things side by side" need is already met even in
  this crude form.
- **Real, confirmed limitations of this v1, not yet solved:**
  - **Grand-staff instruments (Harp, Piano, etc.) can't be split per
    occurrence yet.** The raw MusicXML often has only ONE `<part>`
    internally declaring 2 staves, which music21 auto-splits into two
    Part objects DURING its own parsing - meaning our natural-key/
    occurrence-index system (built from music21's already-split
    parts) and this feature's raw-XML-based extraction (which only
    ever sees the one real `<part>` declaration) are counting two
    structurally different things. Confirmed directly against a real
    file, not assumed. Currently falls back to matching by name alone
    and returning the FULL raw part (both staves combined) - both
    "occurrences" of such an instrument show the same combined
    notation for now, not a clean per-staff split.
  - **Merged (multi-identity) instruments only preview their FIRST
    identity**, not a combined view of everything that was merged
    together - same "first-selected" precedent used elsewhere for
    naming, but a real, known gap here, not a full solution.
  - **~~Qt's SVG renderer skips nested `<svg>` elements~~ — FOUND AND
    FIXED.** This turned out to be a real, serious bug, not a minor
    fidelity issue - user reported the preview window was rendering
    COMPLETELY BLANK (just a correctly-sized white page). Traced
    directly: Verovio nests ALL actual musical content (staves,
    noteheads, everything) inside a second, inner `<svg viewBox="...">`
    used purely to establish a scaled coordinate system - Qt's
    renderer (SVG Tiny 1.2 profile) silently discards any nested
    `<svg>` entirely, which was discarding essentially the whole
    page. Fixed in `notation_preview.py`
    (`render_musicxml_to_svg_pages`/`_flatten_nested_svg`) by
    converting every non-outermost `<svg>` into an equivalent
    `<g transform="scale(...)">` - computing the scale from the
    inner element's own viewBox rather than hardcoding a fixed
    factor (verified as 0.1 for a real page, generalized rather than
    assumed constant). Verified through the full real UI click path,
    not just the isolated function: renderer now reports valid,
    correctly-bounded, non-empty content.
    - **~~Text labels (instrument name, measure numbers, "mute")
      missing~~ — FOUND AND FIXED.** User confirmed the actual notes/
      staves/dynamics/slurs render correctly after the nested-svg fix
      above, but text labels were still missing. Traced to a SEPARATE
      pattern: Verovio zeroes out a `<text font-size="0px">` element's
      own size and puts the real size on a nested `<tspan>` instead -
      Qt's renderer couldn't handle it, throwing "Point size <= 0" and
      "Could not add child element" warnings. Fixed in
      `notation_preview.py` (`_flatten_text_labels`) by collapsing
      the pattern into a single flat `<text font-size="Npx">`. First
      version of the fix assumed exactly 2 levels of `<tspan>`
      nesting and missed the "mute" case specifically, which turned
      out to use 3 levels (an extra `class="rend"` wrapper for text
      directions vs. instrument names/measure numbers) - rewritten to
      match an arbitrary number of wrapper levels generically instead
      of a hardcoded count. Verified all 7 real occurrences in a test
      file are now fixed, including the previously-missed case.
  - **~~No way to zoom out or fit the window~~ — FIXED.** Window
    previously always opened at the SVG's raw/full page size (e.g.
    2100x2970), far larger than the window itself, with no way to see
    the whole page. Added Zoom In/Out, a zoom percentage readout, and
    a "Fit to Window" button that scales to show the whole page -
    computed from the viewport's ACTUAL size, not a guess, and
    specifically computed in `showEvent()` rather than `__init__` (the
    viewport doesn't report a real size until the window is genuinely
    shown and laid out - same class of gotcha as `isVisible()`
    elsewhere in this project). Auto-fits once on first open (so the
    window is immediately usable without any manual action) without
    re-fitting on every subsequent show, and PRESERVES the user's
    current zoom level when navigating between pages (matches normal
    document-viewer behavior) rather than resetting on every page
    turn - verified specifically against a real multi-page instrument,
    not just a single-page one.
- New dependency: `verovio` (not yet reflected in a requirements.txt,
  since none exists in the environment this was built in - user needs
  to add it to their own).
- Still fully pending, not started: opt-in per-window highlighting
  scoped to a side panel mirroring the tree, multi-select, the small
  fixed color palette this would need, and "preview whole score" as a
  wider-scoped instance of the same mechanism. See the original design
  notes below for the full intended shape.

Idea: a way to visually confirm that a detected articulation group
really represents what its label claims, by rendering the actual
notation rather than trusting a text label in the tree. Motivated
directly by how much of THIS session's work was exactly this kind of
ambiguity - Horns 3/4 showing zero notes, trill half-step vs. whole-
step, artificial harmonic pitch correction, tremolo flag-count
ambiguity, sul pont/col legno overlap - all things a visual check
would have resolved instantly instead of requiring XML archaeology or
tabbing back into the notation software.

**Confirmed technically feasible**: [Verovio](https://verovio.org)
(`pip install verovio`) is a real, actively maintained library (C++
core, genuine Python bindings via SWIG, not just a JS-only tool) that
renders MusicXML directly to SVG. LGPL-3.0, compatible with this
project's GPLv3. No browser/web engine needed - SVG output displays
natively in PyQt via `QSvgWidget` (`PyQt6.QtSvg`). Verified as
current/maintained via PyPI, GitHub, and package-health analysis
before considering it, not assumed from memory. OpenSheetMusicDisplay
(OSMD) is the more popular/mature renderer overall but is JS-only,
meaning it would need a `QWebEngineView` embedded (a much heavier
dependency) - Verovio avoids that entirely.

**Architectural approach, decided**: render a real, EXTRACTED part
straight from the original MusicXML (correct clef, key, rhythm,
barring, beaming - all real, none of it reconstructed by us), NOT
something rebuilt from our internal Track/Group note data (which is
just flat note lists with no measure/voice/beaming structure at all -
re-deriving real notation from that would mean solving most of what
makes notation software hard in the first place). This is what makes
a per-instrument preview the SIMPLER technical path, not a
compromise - pulling one part out of a real score is much easier than
synthesizing notation from scratch.

**UI approach, decided**:
- A "Preview" button per instrument (not a modal dialog, not embedded
  in the main window) opens a separate, independent, non-modal window.
  Multiple preview windows can be open simultaneously (e.g. comparing
  two instruments' parts side by side), since each is independent -
  this is the detail that ruled out a single reused preview
  window/dialog.
- Each preview window has its OWN side panel mirroring the
  articulation tree, scoped to just that instrument, used PURELY as an
  opt-in highlighter - deliberately NOT sharing state with the main
  window's checkbox selection (which drives merge/rename), to avoid
  cross-wired confusion between two different meanings of "selected."
- Multi-select highlighting supported (compare several articulation
  groups within one part at once). Color only ever applies to
  what's actively selected in that window's side panel - never a
  fixed "color everything" scheme - which is what avoids the
  legitimate worry about a 25-instrument score turning into a
  color-coded mess: nothing is colored unless the user opts in to
  highlighting it, and only within one instrument's preview at a time.
- "Preview whole score" is NOT a separate feature - it's the same
  window/panel mechanism, just scoped to every instrument instead of
  one, extracting the full score instead of a single part.
- Once multi-select highlighting is built, will need a small fixed
  color palette (~4-6 colors, cycled/assigned per selection) rather
  than unbounded arbitrary colors - not solved yet, just flagged as a
  real decision waiting whenever this gets built.

**Priority**: explicitly below Profiles, Auto Divisi/Solo, and Auto
Condensing. This is a trust/debugging aid layered on top of the tool,
not a functional gap in its core job (producing correctly-routed
MIDI) - worth keeping designed and logged, not worth pulling focus
from the roadmap above.



- **Velocity humanizer.** A random multiplier layered on top of the
  fixed dynamics-mapping velocity, adjustable scale, off by default
  via a checkbox. Real design questions to settle when this is built,
  not now:
  - Distribution shape - leaning gaussian/bell-curve (clusters near
    the target value, occasional bigger swings) over uniform random,
    since that reads as more "human."
  - Percentage vs. absolute range - a percentage behaves very
    differently at `ppp` (velocity 16, so ±10% is negligible) vs.
    `ff` (112, so ±10% is a real swing); an absolute range avoids
    that but has the opposite problem at the quiet end. Needs a
    deliberate choice, not a default-to-whichever's-easier.
  - Deterministic seeding (e.g. from note offset+pitch) rather than
    true randomness on every export - otherwise re-exporting after an
    unrelated small tweak reshuffles every note's humanization, which
    would be frustrating during iterative export-and-check work.
  - Should apply at EXPORT time, layered on top of the base
    dynamics-mapped velocity, not baked into note data during
    parsing - so toggling it on/off doesn't require reloading the
    file.
- **Custom keyword map / user-defined technique categories.** Letting
  a user define their own technique (beyond the built-in pizzicato/
  mute/flutter/sul pont/sul tasto/col legno) and get it separated into
  its own track. Much later, not urgent. Two real implications when it
  happens:
  - `STATE_KEYWORD_CATEGORIES` in `parser.py` is currently a hardcoded
    Python list - true user-defined categories means this becomes
    data-driven from Settings instead, a real structural change, not
    just a UI addition.
  - Start/end should be presented as one obviously-paired unit in the
    UI rather than two independent rows (current Keyword Mapping UI
    already has this same weakness for the built-in categories, e.g.
    "Pizzicato (start)" / "Pizzicato end (arco)" read as unrelated
    rows today - worth revisiting for ALL categories when this is
    tackled, not just new custom ones).

## Next planned milestone

- **~~Settings dialog~~ — DONE (two pages).** Sidebar list + detail
  panel framework (`ui/settings_dialog.py`), persisted to
  `settings.json` directly in the project root (not hidden, not in
  the user's home directory - deliberate choice, see settings.py).
  Both pages read/write the shared `settings` instance live, so edits
  take effect on the next file load with no restart needed, and both
  have a page-level "Reset All to Defaults" with a confirmation
  dialog (per-item Reset buttons stay one-click, no confirmation -
  only the "wipe everything on this page" action warns first).
  - **Keyword Mapping**: the pizz./arco/mute/senza-sord./flutter/sul
    pont./sul tasto/col legno word lists that used to be hardcoded in
    `parser.py` are now user-editable (add/remove/reset per category).
  - **Dynamics Mapping**: the p/mf/f/etc. -> velocity (0-127) table
    that used to be hardcoded in `parser.py` is now user-editable via
    spin boxes, one per dynamic marking.

- **~~Track/Session data model~~ — DONE.** Three-tier model (Track →
  Group → Instrument, each with a permanent-identity layer beneath a
  mutable/mergeable layer) implemented and verified, including
  instrument-level merge/split with cross-identity group un-merging.
- **~~Track-list UI~~ — DONE.** QTreeWidget-based track list (toolbar:
  Open/Import, Export, Merge, Auto Merge, Rename; checkboxes as pure
  selection, not export-inclusion; "M" indicator with hover tooltip
  and double-click-to-split; double-click-to-rename).
- **~~Export inclusion~~ — DONE.** A single toolbar "Export" action
  opens a dedicated dialog: its own inclusion tree (separate from the
  main window's selection tree - `Group.included`/`Instrument.included`),
  a destination folder field + Browse, a filename field (Export All
  only), and both export modes (Export All / Export Per Instrument)
  live in the same dialog. Unchecking an instrument disables its
  articulation rows without clearing their individual included state.
- **~~Visual theme~~ — DONE (light).** Flat, warm/creamy palette in
  `ui/theme.py`, applied globally. A bronze/dark "luxury" orchestral
  variant was discussed and a starter palette proposed, but not yet
  built - would be a second dict + a switch, not a rewrite.

## UI polish (known, deliberately deferred)

- **Tree collapse/expand state is lost on every merge/split/rename**,
  since `refresh_tree()` currently rebuilds the whole tree from
  scratch rather than updating incrementally. Scroll position was
  fixed alongside this exact same root cause (see below) via simple
  capture/restore around the rebuild - collapse/expand state could
  likely use the same pattern (snapshot which instrument
  names/natural-keys were expanded before clearing, re-expand them
  after rebuild) rather than needing full incremental updates.
- **~~Merged rows jump to the bottom~~ — DONE.** `merge_groups`,
  `split_group`, `merge_instruments`, and `split_instrument` all now
  insert their result(s) at the position the original item(s)
  occupied, instead of appending to the end - verified directly
  (including through the real UI click path, not just the data
  layer). One known, minor, NOT fixed sub-detail: when a merged
  group/instrument is later split back apart, the split results land
  in the correct reclaimed position RANGE, but their exact order
  within that range reflects the order they were originally selected
  in for the merge (first-clicked, second-clicked), not necessarily
  their original pre-merge relative order - a cosmetic distinction,
  not a "pushed to the bottom" regression.
  Scroll position was also fixed (same root cause - `refresh_tree()`'s
  full clear()+rebuild was resetting scroll to the top on every
  routine action, not just merge - also affected e.g. toggling the KS
  checkbox): now captured before clear() and restored after rebuild.
- **New feature surfaced by the above:** manual instrument/track
  reordering (drag-and-drop or up/down controls) - once ordering is
  something the data model tracks deliberately rather than "whatever
  order things were appended," letting the user manually reorder
  becomes a natural, wanted feature, not just a bug fix. Also now the
  natural place to note: exported MIDI track order still follows
  `Instrument.groups`/`Session.instruments` list order, which is
  correct/stable now that merge/split preserve position, but still
  has no explicit user-facing reordering control of its own.
- **Per-instrument export filename prefix (opt-in).** Currently
  per-instrument files are named just from the instrument (e.g.
  "Violins 1.mid"). Idea: a checkbox in the export dialog ("Use base
  name as prefix"), unchecked by default so today's behavior doesn't
  change - when checked, reuses the existing "File name" field
  (stripped of `.mid`) as a prefix for every per-instrument file too
  (e.g. "MyPiece - Violins 1.mid"). Chosen over always-on or a second
  dedicated field since opinions on this clearly differ per-user and
  it reuses a field that already exists.
- **Fixed a real Qt/PyQt6 row-height bug** (not backlog, just worth
  remembering): `QTreeWidgetItem.setSizeHint(col, QSize(-1, h))` is
  silently discarded by PyQt6 - width must be non-negative (`0` works)
  or the size hint doesn't stick at all. Not documented behavior,
  found by checking actual returned values directly. Both trees now
  use a fixed `ROW_HEIGHT` to prevent Qt's QSS-padding-driven height
  recomputation from drifting upward on repeated collapse/expand.

## Known parsing/data gaps

- **Unpitched percussion is not parsed at all.** `Unpitched` objects
  aren't `Note`/`Chord`, so they're silently skipped by
  `get_part_articulation_groups`. Needs its own detection path since
  there's no pitch, only instrument/sound identity. No clear plan yet
  for how this should look.
- **Horns 3/4 (Sibelius export) show zero notes despite the composer
  confirming they're not tacet.** Never diagnosed - suspected Sibelius
  export quirk, but unconfirmed. Low priority, but a real correctness
  gap.
- **Multi-voice note ordering is assumed, not guaranteed.** Our timeline
  logic (pizzicato/mute/dynamics state tracking) assumes notes come out
  of `part.flatten().notes` in offset order. Held true for all current
  test files, but dense multi-voice writing could break this. Worth a
  dedicated stress-test file.
- **Articulation/technique keyword lists are a small hardcoded English
  vocabulary** (`pizz`, `arco`, `mute`, `con sord`, etc. in
  `parser.py`). Different composers, languages, and notation software
  will phrase directions differently. Will need to grow, likely into
  something user-editable - a direct prerequisite for sample-library
  profiles being reliable.
- **Filename sanitization has a minor cosmetic bug:** instrument names
  with commas (e.g. "Bassoons 1, 2") become "Bassoons 1_ 2.mid" in
  per-instrument export - functional but ugly. Never fixed, low
  priority.

## Settings dialog - planned future pages

The sidebar+detail framework exists now with two working pages
(Keyword Mapping, Dynamics Mapping - see "Next planned milestone"
above). Categories already committed to for future pages:

- **CC11 dynamics-curve mapping** - downstream of profiles. (NOT
  Sample library profiles itself - that turned out to warrant its own
  standalone Profile Manager window rather than a Settings page, since
  profiles are an actively-worked-in growing library rather than small
  global config - see "Roadmap priority" above and the dedicated
  section below for full status.)
- **Realization-strategy defaults** for tremolo/arpeggio/glissando
  (global default, before profile/per-track overrides - see
  "Note-transformation features" below).
- **Velocity humanizer settings** (enable checkbox, multiplier scale)
  - see "Newer feature ideas" above.
- **Merge-conflict "remember my decision" preference.** From the
  original Session design discussion: when merging produces
  overlapping notes, the plan was a dialog asking the user how to
  resolve it, with a "remember my decision" checkbox whose choice
  would live here in Settings. The merge-conflict dialog itself was
  never built (current behavior: notes are just left overlapping,
  the simpler default) - so this setting has nothing to control yet,
  but the preference storage location was already decided.

## Grand-staff / divisi duplicates

Instruments that declare multiple staves (`<staves>2</staves>` in
MusicXML) get split into multiple separate music21 `Part` objects,
which show up as duplicate tracks:
- Harp, Marimba, Celesta (genuine two-staff instruments)
- Violin I in some pieces (a *reserved divisi staff* - present even
  when the section doesn't actually divide in a given passage)

**Status: mostly addressed.** The "Auto Merge" toolbar button (first
pass) merges any current instruments sharing the same ORIGINAL part
name, which is exactly the signal these duplicates produce - no
confirmation step before merging yet, and it's a manual click, not
automatic on load, per the earlier decision to keep merging
controllable rather than silent. Tested working via merge/auto-merge
in the app.

Confirmed this isn't just a cosmetic issue: found a glissando in a
harp part that genuinely crosses between the two staves (bass clef
start note, treble clef end note) - so merging isn't just about tidy
track names, it affects whether cross-staff spanners can be resolved
at all.

## Harmonics

- **Artificial harmonics — DONE.** Detected via notehead shape (a
  two-note chord: one `diamond` notehead + one `normal` notehead - the
  standard notation for stopped+touched fingering). The written chord
  is NOT the sounding pitch, so it's corrected: touch interval (P4,
  M3, m3, or P5 above the stopped note) is measured and mapped to a
  verified semitone transposition, collapsing the chord to a single
  note at the real sounding pitch. Unrecognized touch intervals are
  left as literal written pitch but still labeled `ArtificialHarmonic`
  (visible, not silently misfiled as Sustain).
- **Natural harmonics — still an open question, not a bug.** Detected
  via the semantic MusicXML `<harmonic><natural/></harmonic>` tag
  (music21's `StringHarmonic` articulation). Whether the written pitch
  represents the touched node or the already-correct sounding pitch is
  genuinely ambiguous by MusicXML convention and composer-dependent -
  currently exported as literal written pitch, unverified whether
  that's actually correct for this composer's own notation habits.
  Worth settling once there's a real natural-harmonic test case to
  check against.

## Note-transformation features ("midi-fy")

These are technique markings that don't map to a simple track/patch
selection - they represent a *transformation* of the written notes
into different actual MIDI events, which is a fundamentally different
problem from everything else in the articulation-labeling system.

- **Arpeggio** - a chord marked `<arpeggiate>`. No sample library has
  an "arpeggio patch" - this needs to become real staggered note-on
  events. Direction-aware (up/down/non-arpeggio) data is already
  retrievable via `ArpeggioMarkSpanner`/`ArpeggioMark.type`, just not
  used yet.
- **Glissando** - now DOES get labeled/separated into its own track
  (added tonight), since some harp libraries have a dedicated gliss
  patch. But for libraries that don't, or for finer manual control,
  this same "expand into real notes" treatment will eventually be
  wanted here too. "Can go either way" depending on the target
  library.
- **Measured (2-note) tremolo export strategy needs revisiting once
  the UI exists.** Currently: labeled by interval quality
  (`Tremolo-M3`, `Tremolo-m3`, etc. - added tonight), and for export,
  both notes' pitch is overridden to the lower of the pair while
  keeping the original written rhythm/duration. This was a
  deliberately conservative default - some libraries have dedicated
  interval-specific tremolo patches that may expect a different
  representation entirely (e.g. a simultaneous dyad rather than a
  bottom-note substitution). Longer-term plan: separate "detection"
  from "realization strategy," where realization strategy becomes a
  choosable setting (global default -> profile default -> per-track
  override in the Session UI), rather than one hardcoded behavior.
- **~~Single-note tremolo flag-count ambiguity~~ — DONE, built as the
  first real "midi-fy" feature (generating actual new MIDI events, not
  just relabeling existing notes - a genuinely new category for this
  app).** The originally-proposed FIXED heuristic (1-2 flags =
  measured, 3+ = unmeasured) was deliberately NOT what got built - per
  design discussion, the threshold is instead a USER-CONTROLLED,
  PER-SESSION setting (not a global Settings default), since the right
  threshold genuinely depends on the piece (a 3-flag tremolo means
  something different in a slow piece than a fast one).
  - **New `core/midifi.py` module** - the shared foundation intended
    for future midi-fy features too (tremolo spanners, glissando,
    legato), not just this one. `MidifiConfig` holds per-feature
    parameters (currently just `tremolo_min_unmeasured_flags`).
    `resolve_tremolo_midifi()` realizes any single-note tremolo below
    the threshold into 2^N literal discrete repeated notes (N = flag
    count) evenly dividing the original note's duration - verified
    this math against the original real-world example that motivated
    the whole feature (an 8th note with 1 flag becoming two 16th
    notes).
  - **Rebuild strategy, confirmed via design discussion**: applying a
    changed threshold triggers a FULL SESSION REBUILD (re-parse from
    the original file with the new config), not surgical in-place
    patching - consistent with how Profile reapplication already
    works, chosen specifically because it composes correctly once
    MULTIPLE midi-fy features exist (each rebuild reapplies the WHOLE
    current config together, so opening one tool can never silently
    discard another's settings). Known, accepted tradeoff (not new -
    same one already accepted for Profile reapplication): a rebuild
    discards manual merges/renames made since the file was loaded -
    the UI warns about this with a confirmation before proceeding.
  - **Session-level persistence**: `Session.midifi_config` (same
    pattern as `Session.tempo_events`) survives session save/load -
    unlike tempo (which is deterministically re-derivable from the
    score, so needs no real serialization), midifi_config is a genuine
    USER CHOICE, so it's actually serialized into session.json and
    reapplied (both to the config field AND by re-running `load_score`
    with it) on reload - verified directly that a saved threshold
    correctly regenerates the exact same realized tremolo notes after
    a full save/reload round trip, not just that the number survives.
  - **Auto-merge with full split-reversibility**: midi-fied notes get
    a distinguishable `"Midifi+<base_label>"` prefix (e.g.
    "Midifi+Sustain") rather than silently blending into whatever
    label they'd otherwise get - `Session.merge_midifi_variants()`
    (direct structural adaptation of the already-proven
    `merge_accent_variants` pattern) folds them into their matching
    base bucket on demand, fully reversible via the existing group
    split mechanism. This is what makes the concrete motivating
    example work correctly: a spiccato passage with an occasional
    tremolo-marked note ends up looking like every other spiccato
    note after merging, not stuck in its own separate track forever.
    A generic label PREFIX (not a routing dimension like divisi/solo)
    was the deliberate choice here - unlike divisi/solo, midi-fied
    notes should end up combined with the REST of the SAME
    instrument, never become their own separate instrument.
  - **UI**: a standalone `Midi-fy` dialog (menu-accessible, NOT a
    Settings page - matches the "per-song, not global" design
    decision), pre-fills the CURRENT session's threshold, warns before
    rebuilding. Plus a "Merge Midi-fy" toolbar button alongside the
    existing "Merge Accents" one.
  - **Real debugging detour worth remembering**: spent significant
    effort chasing what looked like a serious, general music21 bug
    (newly-inserted notes silently vanishing) before discovering it
    was an artifact of testing against an unrealistic bare
    `stream.Part()` (no Measure nesting) rather than genuinely parsed
    MusicXML - re-verified directly against real parsed data (proper
    Measure structure, matching how this app always actually loads
    files) and the implementation works correctly regardless of
    insertion order there. Worth remembering for next time: always
    verify note-insertion mechanics against REAL parsed structure, not
    a hand-built bare Stream, before concluding something is a genuine
    music21 limitation.
  - Only applies to plain Notes, not Chords, even though a Chord could
    theoretically carry a Tremolo expression (e.g. a tremolo chord in
    piano writing) - deliberately out of scope, matching the "stay
    within defined scope, don't guess" pattern already used for
    divisi's 2-pitch-only restriction.
  - **Does NOT apply to `TremoloSpanner` (two-pitch) tremolos** - those
    are always measured by definition (alternating between two
    specific written pitches is inherently precise/notated), a
    genuinely different, still-unbuilt problem (see below).
  - **Caveat for whoever builds the NEXT midi-fy feature**: music21's
    importer silently defaults to `numberOfMarks = 3` if a `<tremolo>`
    element is malformed or missing its count entirely (found directly
    in music21's source, `xmlToTremolo`) - meaning an observed "3"
    could occasionally be missing data masquerading as a genuine
    3-flag tremolo. Not currently guarded against.
  - **~~Default threshold~~ — CHANGED from 1 to 3.** User couldn't
    think of a real use case for defaulting to 1 (which meant midi-fy
    was a true no-op unless explicitly touched) - 3 matches real
    notational convention directly (1-2 flags conventionally means
    precise subdivision, 3+ conventionally means "as fast as
    possible") and is a genuinely useful out-of-the-box default, while
    staying fully user-adjustable. Real subtlety handled deliberately:
    the CLASS default is 3 (new sessions), but `MidifiConfig.from_dict`'s
    fallback (used when loading an OLD session file that predates this
    feature, with no `midifi_config` key at all) stays at 1 - an old
    session genuinely had NO midi-fy applied when saved, so reloading
    it should reconstruct that same state, not silently start
    realizing tremolo in a file that never had it happen. Verified
    both paths independently, plus confirmed against real files that
    the new default genuinely changes behavior where it should (found
    496 previously-untouched 1-2 flag tremolo notes across
    `Woods.musicxml`'s strings and marimba that now correctly midify)
    while leaving files with only 3-flag tremolo unaffected either way.
  - **~~Discoverability~~ — dismissible notice banner added, NOT a
    forced dialog.** Real design conversation first: user initially
    considered forcing the Midi-fy dialog open immediately on import
    (worried a user might never discover the feature, then lose
    session work applying it later given the "rebuild from source"
    strategy). Talked through why that's actually fine for tremolo
    specifically (the measured-vs-buzz judgment is about the PIECE,
    settled once, upfront - nothing done later in a session should
    change that answer) but would be actively wrong for glissando
    (whose midi-fy decision is about the TARGET LIBRARY, likely
    profile-scoped rather than session-scoped, so forcing it at
    import time would be answering the question before it's even
    askable) - so no blanket "prompt on import" policy for midi-fy in
    general, decided per-feature instead. Landed on a lighter,
    non-blocking fix: a dismissible banner above the tree (reusing the
    theme's own accent color) shown after import if the score has
    midi-fiable content, with an "Open Midi-fy" shortcut button. Uses
    a NEW, deliberately independent detection pass
    (`detect_midifiable_content`) that does its own minimal parse
    BEFORE any midi-fy realization runs, specifically to avoid over-
    or under-counting a passage that's already been split into several
    notes by an active config. Per-import, not a permanent one-time-
    ever notice.
  - **Two real, unrelated bugs found and fixed while wiring the
    banner in, not part of the main feature**: a missing `QLabel`
    import that would have crashed the app on startup (caught
    immediately by actually running the code, not just a syntax
    check), and `close_file()` never disabling the midi-fy actions or
    hiding the banner - a genuine pre-existing gap, unrelated to
    tremolo specifically, found and fixed alongside this work.
  - **Environment note**: this work started from a FULL workspace
    reset (fresh container, project gone entirely) - recovered by
    restoring from the last delivered zip and reinstalling
    dependencies from scratch, verified via compile checks before any
    new work began.

## Sample library profiles (EW, Spitfire, Orchestral Tools, etc.)

**No longer distant-future - substantially built tonight, IN
PROGRESS.** See "Roadmap priority" at the top of this file for full
current status (what's done vs. the real remaining gaps, especially
keyswitch export). This section now just tracks the pieces from the
original speculative list that are NOT yet covered by what's built:

- **~~Keyswitch/MIDI-CC insertion at export time~~ — DONE.**
  `exporter.py` now flattens an instrument's included groups into ONE
  track (with keyswitch note-ons inserted at every point the active
  articulation bucket changes) when both `Instrument.keyswitch_enabled`
  and the assigned profile's `keyswitch_enabled` are True - both the
  combined-file and per-instrument export paths use the same shared
  logic (`_build_instrument_export_tracks`). Groups with no matching
  inventory item (`Group.profile_item is None`) are still folded into
  the flattened track but never trigger a keyswitch. Verified against
  real data: correct track-count reduction, correct keyswitch note
  numbers/velocity, correct re-triggering on every bucket transition
  (not just once), and unaffected instruments still export normally.
  - **Known, accepted limitation**: if two different groups have notes
    at the exact same offset (a genuinely simultaneous multi-
    articulation moment), the inserted keyswitch note-on could
    collide with real notes from the other group at that instant.
    Not solved - deliberately accepted as a rare edge case per
    design discussion, revisit only if it actually comes up in
    practice.
  - MIDI CC-based switching (as opposed to note-based keyswitching)
    is still not built - only note-on keyswitches exist right now.
- Per-library note ranges - not yet part of the Profile/InventoryItem
  data model at all; would need a new field if wanted.
- Realization-strategy defaults for tremolo/arpeggio/glissando (see
  the "Note-transformation features" section above) - not yet
  connected to Profiles; still a separate, unbuilt piece.
- CC11 (Expression) dynamics-curve mapping - see "Dynamics / velocity"
  below - still downstream/unbuilt.
- Auto-assigning a profile to an instrument (e.g. guessing from
  instrument name) - explicitly deferred during design as "a
  different task," not started.

## Dynamics / velocity

- **~~Velocity mapping is user-configurable~~ — DONE.** Was a hardcoded
  step-function table in `parser.py`; now lives in `Settings.dynamics_mapping`,
  editable via the Dynamics Mapping settings page (see "Next planned
  milestone" above). Still a step function, not interpolated - see
  hairpins note below.
- **Hairpins (crescendo/diminuendo) are NOT interpolated.** A note in
  the middle of a written crescendo currently just keeps the last
  named dynamic's velocity - no gradual ramp. Deferred because hairpin
  spanner endpoints proved fragile to resolve reliably (same shape of
  issue as the glissando endpoint investigation) - revisit once
  there's a real need.
- **CC11 (Expression) continuous dynamics curves are a separate,
  larger feature**, not just "velocity but as a CC." Needs its own
  design: which CC number (CC11 vs CC1 vs a library-specific macro
  varies by library), curve shape/range conventions, and genuine
  interpolation over time within sustained notes. Belongs downstream
  of both Session (per-project override) and Profiles (per-library
  default) - not before them.
- **Velocity humanizer** - see "Newer feature ideas" above.

## Tempo

- **~~Tempo was completely missing from exported MIDI~~ — DONE.**
  `parser.get_tempo_timeline()` + `Session.tempo_events` +
  `exporter._insert_tempo_events()`. See "Roadmap priority" /
  session-log for full detail. Handles discrete, explicit tempo
  values only (either a real notated metronome marking, or a
  `<sound tempo="X">` playback hint attached to a tempo word like
  "Adagio" - both verified against real files). Falls back to 120 BPM
  if no tempo marking exists anywhere in the score.
- **Gradual tempo changes (accelerando/ritardando/rallentando) are
  NOT recognized - confirmed, deliberate scope decision, not a bug.**
  A bare "Accel."/"Rit." marking with no accompanying numeric tempo
  hint doesn't even produce a `MetronomeMark` in music21 - it becomes
  a plain `TextExpression` (the same generic object used for pizz./
  mute/sul pont./etc.), invisible to `get_tempo_timeline()`. Verified
  directly with a synthetic test file, not assumed. Silently ignored
  rather than guessed at - same reasoning already applied to dynamics
  hairpins (see "Dynamics / velocity" above): a continuous, gradual
  change with no single defined target value is fragile to interpolate
  correctly and often not even well-defined by the composer in the
  first place. Out of scope for the same reason hairpin interpolation
  is - if ever revisited, should probably be designed alongside
  hairpins as one shared "continuous change" feature, not two separate
  ad hoc systems.
  - **"A Tempo" is a real exception and already works today** - it
    typically DOES carry an explicit `<sound tempo="X">` hint (since
    it just means "return to a known prior value" the notation
    software already has numerically), and that IS picked up correctly
    by the existing implementation - verified directly. Not a gap,
    just worth distinguishing from true accelerando/ritardando
    markings, which don't carry that kind of concrete data.

## Not yet scoped / farther out

- Packaging/distribution as a standalone app (PyInstaller/Nuitka)
  rather than "run from source in a venv" - relevant once this isn't
  just for personal use.
- Batch processing - exporting multiple MusicXML files in one pass
  (plausible given orchestral projects often span multiple
  movements/cues).
- Cross-notation-software testing for the sounding-pitch conversion
  (`load_score`'s `toSoundingPitch()` call). Confirmed correct for
  Dorico's "Concert Pitch" export toggle. Not yet tested against
  Sibelius or MuseScore's equivalent - there's a real risk of
  double-transposition if a program bakes sounding pitch into
  `<pitch>` while still declaring a non-zero `<transpose>` (see
  parser.py discussion).

## Auto Divisi / Solo detection

**DONE - both built, tested, and confirmed zero-regression on real
files.** Substantially UPGRADED since first built: Divisi and Solo now
both produce genuinely SEPARATE Instruments, not just separate Groups
under one shared instrument - see the dedicated subsection below for
why and how, added after a real design conversation about DAW/patch-
assignment implications.

- **~~Solo/Tutti lives in STATE_KEYWORD_CATEGORIES~~ — SUPERSEDED.**
  Originally built as just another state-keyword category (same
  mechanism as pizz/mute), but pulled OUT of that mechanism during the
  separate-instrument upgrade below - solo isn't "another technique to
  combine with others" the way pizzicato/mute are, it's an
  orchestration-level ROUTING decision (which physical player(s) are
  playing), the same category as divisi. Detection words unchanged
  (`solo_on = ["solo"]`, `solo_off = ["tutti", "a2", "a3", "a4",
  "unis", "unison"]`, user-editable via Settings same as always) - only
  HOW the detection result gets used downstream changed.

### Divisi/Solo as separate Instruments (not just separate Groups)

**Real design gap found and fixed, via user-initiated design
conversation, not a bug report.** User was designing a "legato
support" feature and, while reasoning through a friction point,
independently spotted that the ORIGINAL divisi/solo implementation had
a real latent problem: divisi/solo content was only a separate GROUP
under the SAME Instrument as the rest of the section - meaning if that
instrument had a keyswitch-enabled Profile assigned, a divisi/solo
passage was only protected from being swept into the flattened
keyswitch track by ACCIDENT, not by design.

- **Root cause, verified directly in the code before proposing a fix**:
  Profile keyword-matching is EXACT STRING equality against a track's
  full label - and a divisi/solo track's label included the routing
  prefix baked in (e.g. `"DivisiTop+Sustain"`, not just `"Sustain"`).
  So unless a user happened to type that exact combined string into
  Keyword Matching, the divisi/solo group would never match any
  inventory item, landing in the "unmatched" bucket - which (per the
  earlier unmatched-groups export fix) already correctly stays as its
  own separate, un-flattened track. Real protection, but coincidental
  - if anyone ever DID add that exact combined label (e.g. copying it
  from the tree, trying to be thorough), the divisi/solo passage would
  get silently swept into the flattened track, permanently fusing
  Top/Bottom pitches together under keyswitch cues that don't
  distinguish them.
- **Fix: divisi/solo now produce genuinely separate `Instrument`
  objects**, not just separate `Group`s. This makes the safety
  property STRUCTURAL rather than coincidental - keyswitch flattening
  only ever operates on one instrument's own groups, so a divisi/solo
  instrument can never be reached by it regardless of what any
  Profile's keyword matching does. Verified directly, not just
  reasoned about: assigning a keyswitch-enabled profile to a "main"
  instrument leaves a sibling Divisi-Top instrument's `.profile`/
  `.keyswitch_enabled` completely untouched.
- **Also motivated by real DAW/patch-assignment reasoning, not just
  the keyswitch edge case**: a divisi or solo passage very often needs
  a genuinely DIFFERENT sample-library patch than the full section (a
  solo violin patch vs. the section patch; a 2-way divisi patch vs.
  the a-section patch) - modeling them as separate Instruments means
  each gets its own independent Profile assignment, own KS toggle, own
  everything, matching how they'd actually be routed in a real DAW
  session.
- **Architecture, for both cases**: `parser.get_part_articulation_groups`
  now returns `{(routing, label): notes}` instead of `{label: notes}`
  - `routing` is `None` (normal/tutti), `"DivisiTop"`,
  `"DivisiBottom"`, or `"Solo"`, a dimension kept DELIBERATELY separate
  from the articulation label (routing answers "which player(s)",
  label answers "what technique"). `Session.from_score()` buckets by
  routing FIRST, creating one Instrument per non-empty bucket, each
  with its own SYNTHESIZED `InstrumentIdentity` (gained a `variant`
  field: `None`/`"DivisiTop"`/`"DivisiBottom"`/`"Solo"`, included in
  `natural_key` as a THIRD element - `(original_name, occurrence_index,
  variant)`, always 3-tuple shape now, not conditionally 2 or 3).
  Display name gets a suffix, e.g. "Violin I (Divisi Top)".
- **Ripple effects, all found and fixed, not just the core change**:
  - `session_file.py` needed ZERO code changes - serialization/
    deserialization already treated `natural_key` as a fully generic
    tuple, confirmed by reading the code AND by an actual real save/
    load round-trip test with Solo-derived instrument content, not
    just trusting the code looked generic enough.
  - `notation_preview.py`'s `extract_part_xml` DID need a fix - it
    unpacked exactly 2 elements from `natural_key`, which would have
    raised on the new 3-tuple. Fixed to read just the first two
    (name, occurrence) and deliberately IGNORE variant - a Divisi/
    Solo-derived instrument has no separate `<part>` in the source
    file to extract, so previewing one correctly falls back to
    showing the same real underlying part (genuinely correct
    behavior here, not a compromise - the notation software's own
    rendering shows these distinctions within one staff too, not as
    separate staves).
  - `exporter.py`'s legacy score-based export path (confirmed
    unreachable from the real app via direct search before touching
    it, but fixed anyway rather than leaving known-broken dead code)
    needed its label-unpacking updated for the new tuple key shape.
  - `main_window.py` needed ZERO changes - confirmed directly via a
    full UI-level test - it already just iterates
    `session.instruments` generically, so Solo/Divisi instruments
    showing up as ordinary new rows in the tree required no special
    UI code at all. Direct payoff of having kept the Instrument
    abstraction consistent rather than special-casing divisi/solo
    display earlier.
- **Full regression confirmed clean** across all three real test
  files (identical output, just correctly wrapped in the new
  `(None, label)` shape) and every previous divisi unit test re-run
  (chord-based split, unison duplication/independence, double-stop
  safety, articulation preservation) - all still pass unchanged.

- **Divisi - scoped to 2-way, string-style divisi only** (a4/a3 wind-
  brass "exploding" is a genuinely different problem, not a bigger
  version of this - see reasoning below). Two source conventions
  detected, both gated by an explicit `divisi_on`/`divisi_off` text
  window (deliberate - a 2-note Chord is structurally IDENTICAL
  whether it's a real divisi passage or a double-stop; the text marker
  is the only way to tell them apart, so requiring it avoids
  misreading a double-stop as a section split - verified this
  distinction holds directly):
  - **Chord-based** (`div.` + a 2-note chord in one voice): the
    original Chord is deep-copied whole BEFORE either half is
    mutated down to one pitch (preserves articulations/expressions on
    BOTH resulting notes) - building the second note from scratch
    instead was tried first and found, by testing a Staccato-marked
    divisi chord specifically, to silently lose articulations on that
    side only.
  - **Voice-based** (two real, independent `Voice` streams - can have
    completely different rhythms between them, not just different
    pitches at matching beats): required comparing two independent
    timelines rather than splitting one object. Two real, non-obvious
    music21 mechanics verified directly before relying on them (both
    would have been silent, hard-to-catch bugs otherwise): (1) a
    note's `.offset` when accessed through `measure.voices` is
    MEASURE-relative, not part-absolute - reconstructed as
    `measure.offset + note.offset`; (2) a flattened note's nearest-
    Voice context (via `getContextByClass`) is unreliable after
    flattening - it returned the SAME wrong voice id for every note in
    a real test case, so voice identity is read directly from
    `measure.voices` instead, never recovered post-flatten.
  - **Unison duplication**: an exact (offset, pitch(es), duration)
    match between what would otherwise be Top and Bottom is tagged
    "Both" and duplicated into both resulting tracks. Two real bugs
    found and fixed here during testing, not just theoretical
    concerns:
    1. Initially tagged BOTH the matching top-voice AND bottom-voice
       note objects as "Both" - since the grouping step independently
       duplicates every "Both"-tagged note it encounters, this
       produced FOUR entries for one genuine unison event instead of
       two. Fixed by tagging only one side and removing the other's
       (now-redundant) note from the stream entirely.
    2. `copy.deepcopy()` on a note nested in Voice/Measure structure
       does NOT reliably preserve absolute offset - verified directly
       (a note at real offset 2.0 came back as 0.0 after copying).
       Fixed by explicitly re-setting `.offset` on the duplicate from
       the original's value after copying, rather than trusting the
       copy - this is the SAME safe pattern `exporter.py`'s
       `_build_midi_track` already used (reads `n.offset` from the
       original at insert time, never from a copy's own attribute),
       confirmed by checking that existing code specifically to rule
       out this being a wider, pre-existing bug - it wasn't; the
       existing code was already careful about this, only the new
       divisi duplication code had skipped that carefulness.
  - **Real-world test against Dorico's native Divisi feature (not just
    manually-typed div./unis. text) - confirmed working AS DESIGNED,
    but reveals a real practical limitation worth flagging clearly.**
    Tested against two real files the user built specifically to
    check this: a manually-typed div./unis. text version (works
    correctly, verified - real DivisiTop/DivisiBottom note counts,
    not zero), and a version using Dorico's actual structural Divisi
    feature (does NOT get detected).
    - **Root cause, traced to the raw XML, not guessed at**: Dorico's
      native Divisi feature does NOT emit a div./unis. text marker at
      all - it's purely structural (the split is encoded as two
      Voices, e.g. voice 1 and voice 3, within the SAME staff). Since
      our detection deliberately requires an explicit text marker
      (see above - the whole point is telling a real divisi passage
      apart from an instrument that's just legitimately writing
      multi-voice content, e.g. keyboard/harp writing), it correctly
      does nothing here, per its own design - the two voices' content
      just gets silently combined into one plain "Sustain" bucket
      instead of split. Not literal data loss (confirmed directly -
      all the real notes are still present, just unsplit and
      undifferentiated), but functionally indistinguishable from loss
      from the user's perspective, since the separation itself is
      exactly what they wanted and didn't get.
    - **Separately, in the SAME test file: Dorico also declared
      `<staves>2</staves>` (two staves, two clefs, two key
      signatures) for this instrument, but tagged EVERY note
      `<staff>1</staff>` - none `<staff>2</staff>`.** When music21
      auto-splits a part by its declared staff count, it routes
      purely by that tag, so the second staff's split ends up
      completely empty (0 notes) - not because anything was lost by
      us, but because Dorico's own export never populated that
      second staff's content in the first place, even though it
      declared the staff existed. **Confirmed by the user directly
      inspecting their own source file - this is a Dorico export
      quirk on the source side, not a bug in our parsing/detection.**
      User is investigating this further on their own end; not
      something for us to chase.
    - **Decision, for now**: keep the explicit-text-marker requirement
      exactly as designed - user will need to add "div."/"unis." (or
      whatever equivalent words they configure in Settings) manually
      for divisi to be detected, even when a notation program's own
      structural divisi feature was used to write the passage. A real
      design tension was raised but deliberately NOT resolved yet:
      for STRING instruments specifically, genuine multi-voice content
      arguably implies divisi inherently (a single player can't
      physically produce two independent lines), which could allow
      dropping the marker requirement for that instrument family
      specifically - but doing that safely would need some notion of
      "which instruments are monophonic," which doesn't exist in the
      app yet, and risks misreading legitimate multi-voice writing on
      keyboard/harp-family instruments if applied too broadly.
      Revisit if this comes up again in practice.
    - **Known, low-priority cosmetic side effect**: the genuinely-
      empty duplicate instrument row (0 notes, nothing to show or
      export) still appears in the tree as clutter. Not fixed yet -
      flagged, not actioned, pending the user's own investigation into
      why Dorico's export behaved this way in the first place.
  - **N-way divisi (a3+) explicitly out of scope for now** - real
    string writing rarely needs it, and unlike the 2-way case there's
    no way to unambiguously "duplicate the same shape" for validation.
  - **Wind/brass "a3"/"a4" exploding deliberately treated as a
    DIFFERENT, separate, unbuilt problem, not a generalization of
    this feature.** Key distinction discussed and agreed: string
    divisi output needs no identity ("Divisi Top"/"Divisi Bottom" are
    generic, don't correspond to anything else in the score), while
    wind/brass "a4" exploding usually needs to reconcile with SPECIFIC
    named players (Horn 1, Horn 2...) who likely have other material
    elsewhere in the piece - an identity-reconciliation problem, not a
    note-splitting problem. Loosely the inverse of the existing grand-
    staff/divisi-duplicate merge work (many staves that are really one
    instrument, vs. one staff that's really several instruments) -
    worth designing alongside that existing work if ever tackled,
    not alongside 2-way divisi.
  - Verified end-to-end through the FULL pipeline, not just parser.py
    in isolation: parse -> Session.from_score -> real MIDI export,
    confirming correctly-named, correctly-separated tracks actually
    appear in a real exported file.
  - Full regression confirmed clean across all three real test files -
    identical output where no divisi markers exist (the expected,
    correct no-op), zero DivisiTop/DivisiBottom labels appearing
    anywhere they shouldn't.

## Auto Condensing / Score Condensing

**Design substantially fleshed out - no longer "hardest of the three,
undesigned."** Original framing (fully-automatic detection, judging
"coincidental overlap vs. intentional unison" via heuristics) has been
replaced with a much more tractable **user-directed** design: rather
than the app guessing which passages should condense, the user
explicitly selects which instruments to consider (e.g. Horns 1-4) and
what counts as a match - turning the hard "is this intentional"
judgment call into a well-defined, deterministic query instead of a
heuristic. Real motivating case: pre-orchestrated library patches
(e.g. Spitfire Abbey Road One's "Sparkling Woodwinds" - solo piccolo +
2 flutes + glockenspiel as ONE patch) that no automatic system could
ever correctly infer without being told.

**Design, agreed:**
- User selects 2+ whole INSTRUMENTS (not articulation groups -
  condensing compares each instrument's entire combined note
  timeline, regardless of which articulation a given note belongs to)
  and clicks "Condense," opening a Condense Options dialog.
- **Breadth is fixed, not a variable/threshold**: a moment only counts
  as condensed if ALL selected instruments agree - no partial-subset
  matching (e.g. 3 of 4 horns in unison doesn't count). Reasoning: no
  known sample library ships a "3 of 4 players in unison" patch, so
  partial matching wouldn't correspond to anything usable anyway.
- **"Notes in common" = exact pitch AND exact duration match** at the
  same offset across every selected instrument - not just pitch.
- **"Minimum Count" = minimum CONSECUTIVE run length** (originally a
  point of ambiguity - could have meant a breadth threshold instead,
  resolved: it's purely a duration/run-length filter). This is what
  prevents one coincidental unison note in an otherwise-independent
  running passage from triggering a false-positive condense - the
  exact concern flagged when Auto Condensing was first discussed.
- **Bar range filtering** (e.g. "1-5, 9-12, 18", blank = whole track):
  confirmed technically easy, not hard as originally assumed - music21
  already exposes `note.measureNumber` directly on any note still
  attached to its original parsed stream, verified against real data
  (correctly reported real measure numbers with zero extra
  computation). This becomes one more attribute captured at PARSE
  TIME, same established pattern as velocity/sounding-pitch/technique-
  label mutation (see parser.py). The only genuinely new work is
  ordinary string-range parsing ("1-5, 9-12, 18" -> a set of measure
  numbers), not new infrastructure.
- Condensed result becomes a NEW track in the tree. Condensed tracks
  are restricted: cannot be merged with anything else (their
  contents/identity is a derived, purely-computed thing, not a normal
  mergeable unit).
- **Original tracks are NOT destructively edited.** Per design
  discussion, notes belonging to a condensed stretch get FLAGGED for
  export-exclusion on the original instruments (so the ensemble patch
  and the individual patches don't both trigger for the same passage),
  but the note data itself stays intact - non-destructive, consistent
  with the rest of the app's philosophy. **Real, not-yet-designed data-
  model work**: `Group.included`/`Track` currently only support
  whole-group inclusion toggling - there's no way to express "excluded,
  but only for this specific subset of notes/bars" yet. This is a
  genuinely new capability, not a UI feature layered on existing
  fields.
- Re-editing (reopening Condense Options on an existing condensed
  track, with fields pre-filled to whatever it was last configured
  with) or removing a condensed track should fully recompute from
  scratch each time (clear old exclusion-flags, then apply fresh
  ones) - same "always rebuild clean, never incrementally patch"
  pattern already used successfully for Profile reapplication and
  merge/split, rather than trying to diff/patch prior state.

**Still open / not yet decided:**
- Exact mechanism for per-note (or per-bar-range) export exclusion on
  the original tracks - the real data-model design work flagged
  above.
- What happens visually/structurally when a condensed track's source
  instruments later get merged, split, or removed - not yet
  considered.
- Whether condensed tracks need their own distinct visual treatment
  in the tree (beyond just "can't be merged"), e.g. an indicator
  similar to the "M" merge marker.

## Session save/load

**DONE** - see "Roadmap priority" at the top of this file for the full
summary. This section is kept only as a historical note: originally
not planned at all (Session was deliberately kept in-memory-only
early on, when a session barely held any state worth persisting), and
was re-prioritized once Session started representing real, non-
trivial manual work worth protecting. The "translation layer" concern
mentioned in earlier drafts of this note (Track/Group/Instrument
holding live, non-serializable music21 objects) was resolved by NOT
serializing note data at all - `session_file.py` instead saves
structure keyed by stable natural keys and re-parses the embedded
original score fresh on load, reconstructing the exact saved
Instrument/Group shape directly against the freshly-parsed
tracks/identities.

## Trills - basic oscillation, DONE

Built in 4 deliberate steps (given the size and the real risk of
losing session budget mid-work, which had already happened once
earlier this session via a full environment reset) - each step fully
tested and delivered before the next began: (1) pure realization
logic; (2) the non-destructive on-demand toggle architecture; (3) the
tree UI toggle; (4) rate config in the Midi-fy window.

  **Step 1.** `core/midifi.py` gained `realize_trill_notes()`,
  a genuinely pure function (no music21/stream dependency at all,
  deliberately - operates on plain MIDI note numbers) that alternates
  between a main and upper-auxiliary pitch, evenly dividing a given
  duration into as many notes as the rate implies (minimum 2). Rate
  is `MidifiConfig.trill_notes_per_quarter` (default 8 = 32nd-note-
  rate alternation), added following the exact same
  session-persistence pattern already proven for the tremolo
  threshold, including a deliberately-considered fallback difference
  in `from_dict` (tremolo's old-session fallback had to differ from
  its live default to avoid silently changing already-baked note
  data; trill's fallback safely matches its default instead, since
  trill realization will be toggled per-note on demand rather than
  applied automatically to a whole session on load).

  `parser.py` gained a small refactor alongside this: the trill-
  interval-detection logic that already existed (for the "Trill-M2"/
  "Trill-m2" tree label) was extracted into a reusable
  `get_trill_interval()` helper, used by both the existing labeling
  code and the new realization work, rather than duplicating the
  logic. Verified this refactor is behaviorally identical via a full
  regression pass before building anything on top of it.

  Verified thoroughly, not just via synthetic inputs: basic
  alternation and exact duration-fit, note count correctly scaling
  with duration, the minimum-2-notes floor holding even for very
  short durations, zero/negative inputs failing safely instead of
  crashing, no gaps or overlaps anywhere in a generated sequence -
  AND the full real-data chain end to end (found the actual trill in
  `String_Test_Piece.musicxml`, correctly detected its interval,
  correctly transposed the upper pitch, correctly realized 32 notes
  filling its exact original duration).

  Decisions made along the way, previously flagged as open,
  now settled for the MVP (both explicitly adjustable later, not
  irreversible):
  - Alternation starts on the MAIN pitch, not the upper auxiliary -
    the modern/common convention, not the alternative historical/
    baroque one.
  - Duration-fit: evenly divide across a rounded note count (mirrors
    tremolo's proven approach) rather than hit the exact rate and
    leave a leftover fractional gap - resolves the question BACKLOG.md
    had previously flagged as genuinely undecided.

  **Step 2.** The actual non-destructive toggle mechanism.
  `Track` gained `midifi_toggle_active` (default False, per-track) and
  `get_active_notes(midifi_config)` - returns `self.notes` (the
  literal original list, not even a copy) when the toggle is off, or
  a freshly-computed realization when it's on. `self.notes` itself is
  NEVER mutated by any of this - confirmed directly (the original
  note's Trill expression and duration were both still intact after
  toggling on and reading the realized output). Computed fresh on
  every call rather than cached, deliberately - trill realization is
  cheap, and this sidesteps any stale-cache risk if the rate config
  changes later while a toggle is active.

  The actual wiring (`realize_track_trills`, in `session.py` rather
  than `core/midifi.py`) turned out to need a real architectural
  choice: `parser.py` already imports from `midifi.py`, so `midifi.py`
  importing `get_trill_interval` back from `parser.py` would have
  been a circular import. Resolved by keeping `midifi.py` as pure
  computation with zero `parser.py` dependency, and putting the
  "wire the pure logic to real track data" concern in `session.py`
  instead, which already legitimately depends on both.

  Verified before relying on it: a note held by a `Track`, well after
  the original parsed `Score` object is released and garbage
  collected, still correctly resolves its trill interval via live key-
  signature context lookup (confirmed directly, not assumed) - so no
  parse-time pre-computation/caching of the interval was needed, on-
  demand computation works correctly as-is.

  `Group.get_combined_notes()` and the export pipeline
  (`exporter.py`) were threaded through to accept and pass
  `midifi_config` (3 real call sites, all in `exporter.py`) - verified
  the full chain end to end: toggle on → real alternating notes appear
  in actual exported MIDI; toggle off → instantly back to the
  original single note, no re-parse. Session save/load also updated -
  each track's toggle state is now genuinely persisted (a real user
  choice about export output, same as any other setting) - the
  serialization format changed from a flat per-group key list to
  per-track dicts, with backward compatibility verified directly
  against a hand-constructed old-format file (loads correctly,
  defaults every track's toggle to off, exactly as an old session
  that never had this feature should).

  **One real, pre-existing, UNRELATED discrepancy found and correctly
  ruled out during testing, not chased down further**: a naive
  regression check comparing note/chord OBJECT counts (293 for
  `String_Test_Piece.musicxml`) against actual exported MIDI
  `note_on` EVENT counts (311) revealed a gap - but that comparison
  was never valid to begin with once chords are involved (one Chord
  object legitimately produces multiple `note_on` events). Confirmed
  directly that this exact same gap exists via the pre-step-2-
  equivalent code path too (calling `get_combined_notes()` with no
  `midifi_config` at all), proving it's unrelated to this work.
  Checked one candidate explanation (duplicate pitches within a
  chord) and ruled it out too - genuinely unexplained, but confirmed
  pre-existing and out of scope for trills. Worth a dedicated look
  sometime, logged separately below rather than left silently
  unmentioned.

  **Step 3.** The actual tree UI toggle. New "Midi-fy" tree
  column (a plain checkbox, no label text - the column header already
  provides context, kept compact matching the narrow Preview column's
  precedent). Shown ONLY for a genuine, single-track trill group -
  checked against the underlying `Track.label` (permanent/immutable),
  not `group.name` (which the user may have renamed), so detection
  never breaks from a rename. Hidden entirely - not just disabled -
  for merged groups, non-trill groups, and instrument rows, same
  "empty cell reads clearer than a permanently-greyed control"
  convention already used for KS.

  Toggling calls the exact same `refresh_tree()` every other toggle in
  this app already uses - genuinely instant, confirmed directly (not
  assumed): checked that `self.session` is the literal same object
  before and after toggling, proving no rebuild-from-source ever
  happens, unlike tremolo's threshold change.

  Verified the complete chain through the REAL UI, not just the data
  layer this time: clicking the actual checkbox in the actual tree →
  `Track.midifi_toggle_active` correctly updates → the checkbox
  correctly re-reflects its own state after the refresh → real MIDI
  export correctly reflects 32 realized notes when checked and
  reverts to the original 1 note when unchecked - toggled both
  directions through the real widget, not just set the flag directly.
  Full regression across all three real files confirmed unaffected.

  **Step 4.** Rate configuration in the Midi-fy window. Added a real
  design decision along the way, not just a UI addition: tremolo's
  threshold and trill's rate can't share one uniform Apply behavior,
  because they aren't the same KIND of setting mechanically - tremolo
  realization is destructive/parse-time (needs a full rebuild to
  change), trill realization is computed fresh on demand every call
  (built specifically in step 2 to avoid needing one). Forcing trill
  rate changes through the same rebuild-and-warn flow tremolo needs
  would have quietly defeated the entire point of that architecture.

  Resolved by having `MidifiDialog._apply()` compare old vs. new
  values itself and expose `.requires_rebuild` for the caller to
  branch on, rather than the caller needing to know the difference:
  only shows the "this will rebuild your session" warning when the
  TREMOLO threshold specifically changed; a trill-rate-only change
  applies instantly with no warning at all.

  Verified all of this directly through the real UI, not assumed from
  the design: a trill-rate-only change showed no warning dialog and
  left `self.session` as the literal same object (proving no rebuild
  happened); a tremolo threshold change still correctly showed the
  warning and produced a genuinely new session object; cancelling the
  warning correctly aborted with zero side effects on either setting.

  Also verified the actual payoff this whole 4-step architecture was
  built for, not just each piece in isolation: toggled a trill on at
  the default rate (32 notes), changed the rate via the dialog with
  NO re-toggling, and confirmed the SAME already-toggled trill
  automatically produced 64 notes on the next export - the rate
  change propagated with zero additional user action, exactly as
  step 2's "compute fresh on demand, never cache" design was meant to
  enable. Also confirmed the dialog correctly pre-fills the CURRENT
  session's live values when reopened, not stale defaults.

  Original design context (UI shape, why the non-destructive
  architecture is needed for steps 2-3, the still-open velocity-
  timing question, the classification/defaults design for later):
  - **UI**: a toggle per trill-labeled row in the tree is the primary
    action (not a toolbar-select-then-click flow, and not buried only
    in a dialog) - trill decisions are usually made per-instrument
    based on what patch is actually available, so bulk-apply doesn't
    buy much. The toggle must feel INSTANT - no rebuild-from-source
    warning, unlike tremolo.
  - **This forces a real architectural change, decided to build for
    trills first, retrofit tremolo later, NOT simultaneously.**
    Tremolo's current realization is a destructive parse-time
    rewrite - the original note is mutated in place and the tremolo
    tag is stripped, so there is nothing left in memory to undo from;
    that's WHY tremolo's toggle currently requires a full rebuild
    warning. An instant toggle needs the opposite: keep the original,
    un-midified notes intact somewhere, and treat "midified" as
    something computed fresh on demand and swapped in/out per track,
    never destroying the source data. This mechanism doesn't exist
    yet anywhere in the codebase. Building it for trills (nothing to
    break yet) and only later retrofitting tremolo onto the same
    pattern, once it's proven, rather than migrating a working feature
    and building brand-new infrastructure in the same pass.
    - **Real open technical question this raises**: WHEN does
      velocity/dynamics get applied to a note that's realized
      on-demand rather than once at parse time? Tremolo's dynamics
      pass currently runs once, after all notes (including realized
      ones) exist. Needs an actual answer once this mechanism is
      designed, not just "reuse tremolo's pipeline as-is."
  - **Speed/rate representation: tempo-relative subdivision, not
    absolute Hz** - matches how trills are actually notated (an
    ornament relative to the beat, not a fixed oscillation rate), and
    stays musically correct across tempo changes within a piece.
  - **Still undecided, needs a real answer before more settings layer
    on top**: how the trill's note count interacts with its host
    note's duration - evenly divide the duration with rate as a
    target/average (always fits exactly, rate is approximate), vs.
    hit the exact rate and accept a leftover fractional gap at the
    end of the note. Small decision now, real headache to change once
    curves/humanize depend on the timing model.
  - **MVP scope, decided**: linear speed only, no humanizer, velocity
    taken directly from the dynamic marking (no accent/tenuto layering
    yet - flagged as a real future refinement, not now). Rate/shape/
    curve/velocity-shape/humanizer are all meant to become real
    settings eventually, but only rate is being tackled first - the
    generation function should still take these as real parameters
    with hardcoded defaults now, rather than baking "linear, no
    humanize" into the logic itself, so the future settings work is
    wiring, not restructuring.
  - **Where rate/shape/curve config lives: the Midi-fy window,
    PER-PROJECT, not global Settings.** Once tempo-relative
    subdivision was decided, this stopped being a preference and
    became a musical decision about the specific piece - the same
    reasoning already applied to glissando/legato's Profile-scoping
    above.
  - **Instrument classification (oscillation vs. tremolo-style trill,
    e.g. timpani) is explicitly a SEPARATE later step, after basic
    oscillation trills work** - deliberately sequenced this way.
    Design already agreed for when it's built:
    - Lives in the Midi-fy window too (per-project, editable per
      instrument) - explicitly rejected having it live in Settings
      alongside global defaults, since two places showing "the same
      setting" (one affecting this project, one only affecting future
      projects' starting point) would be genuinely confusing, not
      just redundant.
    - A dedicated "Edit Defaults" button opens the GLOBAL default
      classifications (used to seed new projects) - editing there
      never touches the current project's live settings, and vice
      versa.
    - "Restore Defaults" resets the CURRENT project's classifications
      back to whatever the current global defaults are. Scope: whole-
      project first (decided); per-instrument restore is wanted too,
      but later.
    - A reverse action - "promote this project's current
      classifications to be my new defaults going forward" - agreed
      as worth adding, not yet designed further.
    - Global defaults need a real starting value per instrument type
      (even if wrong/unrefined) rather than any "empty/unset" state -
      deliberately fine to get this wrong initially and tune later,
      just not leave it blank.
    - Treating a trill as a tremolo (timpani-style) is NOT a separate
      mechanism - it's just one of the two values this same
      classification setting can take.

## Checkbox styling and click-anywhere row selection

Two related UI fixes, tackled together since the user raised them in
the same message.

**Checkbox invisibility on macOS dark mode.** Confirmed directly
(grepped theme.py) that `QCheckBox` had ZERO explicit styling
anywhere - it had been relying entirely on native OS rendering this
whole time. That's exactly what made it break: a natively-drawn
dark-mode indicator has no awareness this app's own theme is light,
so it can render with poor/no contrast against the app's own light
row background. Fixed by adding a real `QCheckBox`/
`QCheckBox::indicator` block to theme.py's stylesheet, using the
existing color tokens (accent blue for checked, matching what's
already used elsewhere for consistency) - every pixel now explicitly
controlled rather than deferred to native rendering. Checked state
uses a solid color fill rather than a drawn checkmark glyph,
deliberately - avoids needing an image asset bundled with the app,
and a fill-color difference alone is already clearly readable.
Verified the stylesheet is syntactically valid and actually gets
applied (main.py already calls `app.setStyleSheet(build_stylesheet())`
globally) - actual visual contrast on a real Mac in dark mode can only
be confirmed by the user's own eyes, same limitation as any other
purely visual/rendering question this session.

**Checkboxes were never meant to be the ONLY way to select tracks.**
User clarified a long-standing but never-validated design decision:
`self.tree.setSelectionMode(NoSelection)` had been set explicitly at
some point, disabling ALL native row selection/highlighting entirely
and making the tiny checkbox glyph the sole interaction target - not
what was originally intended. What was actually wanted, confirmed
directly: clicking ANYWHERE on a row (except another embedded control
- Profile button, KS/Midi-fy checkboxes, Preview button) should behave
EXACTLY like clicking that row's own checkbox - a bigger, more
forgiving hit target for the SAME existing toggle, not a second,
separate selection mechanism to build and keep in sync. Framed by the
user as "I don't want to play an FPS game just to hit that checkbox."

This turned out to be structurally much simpler than the initial
proposal (which assumed full native `ExtendedSelection` with Ctrl/
Cmd/Shift semantics, requiring bidirectional sync between two
independent state systems and raising a real question about whether
native multi-select's click order could still drive the existing
merge-naming logic). Once the actual ask was "just a bigger click
target for the existing per-row toggle, every click independently
additive, nothing replaces anything else" - no separate selection
concept was needed at all, and the existing `check_order`-based merge-
naming logic required zero changes.

Implementation required real care around two genuine mechanical risks,
both verified directly rather than assumed, via a real simulated
`QTest.mouseClick` at exact pixel positions (not guessed at from
documentation):

1. **Double-toggle risk on the glyph itself.** Confirmed directly:
   clicking the checkbox glyph fires `itemChanged` (native toggle)
   BEFORE `itemClicked` - meaning a naive "toggle on itemClicked"
   handler would toggle twice for a glyph click (once natively, once
   from the handler), cancelling itself out. Fixed via a guard flag
   set in `on_item_changed` whenever a genuine check-state change (not
   a text rename) is detected, consumed by the very next
   `itemClicked`. The rename-vs-toggle discrimination itself is simple
   and doesn't need any state-tracking: `COL_NAME`'s data can only
   ever change for one of those two reasons, so "text didn't change"
   is a complete, correct signal that it must have been a toggle.

2. **Double-click-to-rename side effect.** `itemClicked` also fires on
   the first half of a double-click, and double-clicking a row is how
   renaming (native Qt inline editor) and splitting (COL_MERGED)
   already work - without a guard, every rename/split attempt would
   ALSO flip the checkbox as an unwanted side effect. Fixed via a
   standard debounce: the actual toggle is delayed by
   `QApplication.doubleClickInterval()`, cancelled in
   `on_item_double_clicked` if a genuine double-click follows within
   that window.

**A real bug found and fixed during testing, not just a theoretical
edge case avoided in advance**: the debounced toggle's own
`setCheckState()` call (from `_perform_pending_toggle`) ALSO fires
`itemChanged`, which was incorrectly setting the SAME glyph-click
guard from point 1 above - even though no `itemClicked` was ever
coming to consume it, since this path is timer-triggered, not a fresh
mouse click. That left a stale guard silently swallowing the very
NEXT real click on that row entirely (confirmed directly: a second
click on an already-toggled row did nothing at all). Fixed with an
explicit `_programmatic_toggle_in_progress` flag, set only around that
one specific internal call, so `on_item_changed` can tell its own
timer-driven toggle apart from a genuine native glyph click.

Visual highlight (background/foreground color) mirrors check state
directly inside `on_item_changed` - deliberately not using Qt's native
row-selection mechanism at all for this, matching the simplified
design: a color derived purely from check state can't drift out of
sync with it, since there's only ever one source of truth, with no
second state to keep synchronized.

Verified thoroughly through real simulated interaction (not just
calling internal methods directly): clicking row text toggles after
the debounce, clicking the glyph directly still produces exactly one
toggle, a genuine double-click does NOT also toggle, the embedded
Preview button still works correctly and is completely unaffected,
the visual highlight correctly mirrors check state in both directions,
and - the actual motivating use case - clicking two different rows in
sequence (via plain row clicks, not the tiny glyph) correctly drives
`check_order` and produces the correct click-order-based merge name,
through a REAL `merge_selected()` call, not just inspecting internal
state.

**A real test-methodology trap hit and correctly diagnosed along the
way**: an early version of the multi-row test appeared to hang/fail
with `check_order` showing only one item after two clicks. Root cause,
found by testing rather than guessing: `visualItemRect()` returns
coordinates in the tree's full virtual/scrollable content space, not
constrained to what's currently visible in a small viewport - the
second target row was genuinely scrolled out of view, so a "click" at
its nominal coordinates hit nothing at all (confirmed directly via a
raw, independent `itemClicked` listener showing zero firings).
Diagnosed with `scrollToItem()` before vs. after comparison, not
assumed - same class of "offscreen/headless environment gotcha" this
project has hit before with `isVisible()` needing a real `.show()`.
Not a bug in the application code at all, purely a test-harness gap.

Full regression confirmed clean across all three real test files
(identical note counts to every prior confirmed baseline).

## Checkbox styling gap #2, and correcting the selection semantics

Two follow-ups to the previous checkbox/selection work, from the same
conversation.

**Remaining checkbox styling gap, found by searching rather than
assuming.** User reported the Midi-fy checkbox looked correctly styled
but others didn't. Both KS and Midi-fy are real `QCheckBox` widgets,
already covered by the earlier fix - so the report pointed at
something else. Grepped for every `ItemIsUserCheckable` usage in the
codebase and found the real gap: the MAIN per-row track-selection
checkboxes (used for the whole click-anywhere-to-select feature) are
NOT `QCheckBox` widgets at all - they're the tree's own native
checkable-item rendering, which Qt styles via a completely different
selector (`QTreeView::indicator`, not `QCheckBox::indicator`) that the
previous fix never touched. Also found, by searching rather than
guessing there'd only be one place: `export_dialog.py` has its own
tree with checkable items, which had the exact same gap. Fixed by
adding a `QTreeView::indicator` block to theme.py matching the same
visual design as the existing `QCheckBox::indicator` rule - applies
globally to both trees since the stylesheet is application-level.

**Selection semantics were built wrong the first time, corrected
here.** The earlier click-anywhere-to-select implementation made every
click independently toggle just that one row, with no "replace the
selection" behavior at all - based on an interpretation that turned
out not to match what was actually wanted. User clarified directly:
standard Finder/Explorer semantics were the actual intent - plain
click selects ONLY that row (deselecting anything else), Cmd/Ctrl-
click toggles just that one row while leaving everything else alone.
Worth being direct about: this was a real misunderstanding on the
first pass, not a refinement.

Implementation added a shared `_enforce_replace_selection(item)`
helper (uncheck everything else, used by both the debounced row-click
path and the native-glyph-click path) and modifier-key detection via
`QApplication.keyboardModifiers()`, captured AT CLICK TIME (not re-
read later when the debounce timer fires, since the key may no longer
be held by then). The native glyph-click case needed its own specific
handling: Qt's own click handling has already performed the toggle by
the time this code sees it (confirmed in the earlier session), so
"replace selection" for a plain glyph click is enforced AFTER the
fact rather than before - there's no way to intercept Qt's native
toggle ahead of it happening.

Verified all five real interaction patterns through actual simulated
clicks with real modifier keys, not just internal state manipulation:
plain click selects only that row; a second plain click on a different
row correctly replaces the selection; Cmd-click adds without
replacing; Cmd-click on an already-checked row toggles it off alone;
a plain click on an already-solely-selected row is a correct no-op.
Also re-verified the native glyph-click path enforces the same
replace-selection behavior, the double-click-doesn't-also-toggle guard
still holds after the rewrite, and the actual real-world payoff this
whole feature exists for - plain-click one row then Cmd-click another,
then a real `merge_selected()` call - still correctly produces
click-order-based merge naming through the corrected semantics.

Full regression confirmed clean across all three real test files.

## Selection semantics corrected again, and the debounce removed for latency

Two more real corrections to the same feature, from a direct, blunt
"you're testing my patience" - worth being honest that this took
three passes to get right, not two.

**The real rule was per-click-TARGET, not per-modifier-key.** The
previous version applied "replace unless Cmd/Ctrl held" uniformly to
BOTH the checkbox glyph AND clicking elsewhere on the row - which was
still wrong. Clarified directly: the checkbox glyph should ALWAYS be
purely additive, full stop, regardless of any modifier - because being
additive-without-needing-a-modifier IS the entire reason the checkbox
exists as a separate thing at all. Making it ALSO sometimes replace
the selection would defeat that purpose entirely. Only clicking
elsewhere on the row (name text, Merged column) follows the
modifier-gated replace-vs-add rule. Fixed by simply removing the
"enforce replace selection" call from the glyph-click reaction branch
entirely - it's now a pure toggle-and-return, no modifier check
needed there at all.

**The debounce was real, felt latency for a problem that turned out
to be harmless either way - removed entirely.** User reported
selection felt "laggy and uncomfortable," which traced directly to
the `QApplication.doubleClickInterval()` debounce added to prevent a
double-click (rename/split) from also toggling the checkbox on its
first click. Reconsidered the actual cost of NOT debouncing: a
double-click-to-rename also leaving that row selected is a sensible,
unsurprising outcome (you just interacted with it), and a double-
click-to-split (COL_MERGED) triggers a full `refresh_tree()` rebuild
regardless, which wipes any selection state either way - so the thing
the debounce was protecting against was never actually harmful.
Removed the whole timer-based mechanism (`_pending_toggle_timer`,
`_pending_toggle_item`, `_pending_toggle_additive`,
`_perform_pending_toggle` all deleted) and apply the toggle
synchronously, immediately, inside `on_tree_item_clicked` itself.

**A real bug caught by reasoning through the refactor before testing,
not found empirically this time**: `_enforce_replace_selection` had
been managing `_programmatic_toggle_in_progress` internally (setting
it True, then False at its own end) - but the caller now needs that
flag held across BOTH that call AND its own subsequent "ensure item is
checked" step as ONE guarded block. Left as-was, the nested call would
have cleared the flag partway through the caller's still-in-progress
work, re-triggering the exact same stale-guard bug pattern found and
fixed once already (a real click on that row afterward getting
silently swallowed). Fixed by moving flag management entirely to the
one remaining caller, since `_enforce_replace_selection` no longer has
multiple call sites competing for the same flag.

Verified thoroughly through real simulated clicks with real modifier
keys, explicitly WITHOUT any wait/delay this time (the whole point
being to confirm the lag is gone): name-click applies instantly with
no wait; a second plain name-click on a different row still correctly
replaces the selection, instantly; the glyph is confirmed additive
even with NO modifier held (the specific case that was wrong before);
a second glyph click on the same item correctly toggles it back off
without touching others; Cmd-click via the name area still adds
without replacing.

**A real test-environment limitation hit and correctly diagnosed,
not worked around by weakening the fix**: `QTest.mouseDClick` produced
zero signal firings for double-click verification, even in a
completely minimal, isolated tree with no application code involved
at all - confirmed this is a genuine offscreen-Qt-platform limitation
in this environment, not a regression, by testing the exact same
double-click simulation outside the app entirely. Rather than chase
an unreliable test method further, verified what actually matters
directly: `Session.split_group()` itself (called by
`on_item_double_clicked`, which had only 2 now-dead debounce-
cancellation lines removed, nothing else touched) still works
correctly when called directly, confirming there's no real regression
risk in the logic itself even though the UI-level double-click
couldn't be automated-verified in this specific environment.

Full regression confirmed clean across all three real test files.

## Tremolo spanner interval detection

Design discussion for tremolo spanner's on/off toggle (the next midi-
fy feature after trills) surfaced a real mistake worth recording
honestly: claimed tremolo spanner labels already carried interval
info ("Tremolo-M3" vs "Tremolo-m2"), pattern-matching from how Trill
already works, without actually checking. They didn't - the label was
just the bare class name "TremoloSpanner". Caught by checking the
actual code rather than continuing to assert it, then corrected
directly with the user rather than silently fixing it and moving on.

This mattered because the user's own reasoning about a real use case -
some owned libraries have dedicated trill patches specifically for
minor/major 3rds, which shouldn't be midi-fied - depends on the
interval actually being visible per-group, exactly the same way trill
already lets a user judge "does this look like something my library
handles."

**Built now, bundled into the design discussion rather than deferred**:
`get_tremolo_spanner_interval()` in parser.py, mirroring
`get_trill_interval()`'s shape but genuinely simpler - a tremolo
spanner's two pitches are BOTH directly written in the score (via
`spanner.getSpannedElements()`, confirmed via real data to always
return exactly 2 elements), so this is a direct interval computation,
no key-signature-based inference needed the way trill required.
`get_note_level_label()` updated to use this for TremoloSpanner
specifically (Glissando, which shares the same spanner-detection loop,
untouched).

Verified against real, not synthetic, data first: `Mysterious_
Journey...musicxml` has real tremolo spanner content across 3
different instruments (Piccolo, Harp, Viola) - EVERY interval found
turned out to be a 3rd (major or minor), directly validating the
motivating use case without needing to go looking for one. Also
found a `Tremolo-P4` in Harp that hadn't shown up in an initial
narrower check - a reminder to scan broadly rather than stop at the
first confirming example.

The chord-to-chord case (mismatched note counts between the two
sides) has no example in any of the 3 real test files, so verified it
directly via constructing a TremoloSpanner between a 2-note and a
3-note chord through music21's own API rather than leaving it
unverified - confirmed the interval correctly uses each side's first
pitch, correctly handles the mismatched count, and gives the same
result regardless of which side of the spanner it's queried from.
Also verified the full label pipeline end-to-end for this case (not
just the raw interval function), and confirmed a plain, unmarked note
is completely unaffected.

One real API-name trap hit and fixed quickly: `TremoloSpanner` lives
in `music21.expressions`, not `music21.spanner` as a first attempt
assumed (an easy mistake given most other spanner-family classes DO
live in `music21.spanner`) - caught immediately via an AttributeError
rather than silently producing a wrong result.

Full regression confirmed clean across all three real test files -
this was a pure additive labeling change, not a behavior change to
anything downstream yet (the actual on/off toggle, and the off-
state's collapse-to-one-sustained-note behavior, are separate, not-
yet-built work - see BACKLOG.md for the full agreed design).

## Tremolo spanner - DONE

Built in 3 deliberate steps (shorter than trill's 4 - no rate
ambiguity to solve here, flag count already fully determines the
realization) - each step fully tested and delivered before the next
began.

- **Tremolo spanner (measured 2-note/chord tremolo).** (1) pure
  realization logic; (2) wiring into the non-destructive toggle
  architecture, generalized beyond what trill needed; (3) tree UI
  toggle - matching trill's mechanism exactly, no dialog/rate-config
  step needed given flag count already fully determines the
  realization.

  **Correction to an earlier claim in this same entry**: previously
  described the CURRENT (pre-toggle) export behavior as "overriding
  both notes' pitch to the lower of the pair, keeping the original
  written rhythm" - checked the actual code before starting step 2 and
  found this placeholder was never actually implemented anywhere in
  the codebase (searched parser.py, exporter.py, and the whole repo
  for any TremoloSpanner pitch-manipulation logic - none exists).
  Confirmed directly what ACTUALLY happens today for a track that
  hasn't had the new toggle wired in: notes export exactly as written,
  both sides at their real, distinct pitches with the original
  rhythm - not collapsed to one pitch at all. This was a second
  instance of trusting an earlier written claim without re-verifying
  it (the first being the "labels already carry interval info"
  mistake corrected earlier) - worth naming as a pattern to watch for,
  not just fixing quietly.

  **Interval detection - DONE.** `get_tremolo_spanner_interval()` in
  `parser.py` (mirroring `get_trill_interval`, but genuinely simpler:
  a tremolo spanner's two pitches are BOTH directly written in the
  score, no key-signature inference needed like trill required).
  Labels now read e.g. "Tremolo-M3"/"Tremolo-m3" instead of a bare
  "TremoloSpanner" - verified against real data across 3 different
  instruments in `Mysterious_Journey...musicxml` (Piccolo, Harp,
  Viola - all real intervals found were 3rds, directly matching a
  real case: some owned libraries have dedicated 3rd-interval trill
  patches that DON'T want to be midi-fied, a decision that needs to
  see the interval to be possible at all). Chord-to-chord case
  verified via direct construction (no real test file has one): uses
  each side's FIRST pitch, correctly handles chords with MISMATCHED
  note counts (e.g. a 2-note chord to a 3-note chord), same result
  regardless of which side of the spanner is queried from.

  **Step 1 - DONE.** Two pure functions in `core/midifi.py`:
  `realize_tremolo_spanner_notes()` (ON-state - alternates between the
  spanner's two sides for 2^flag-count total slots, evenly dividing
  the total duration - the SAME "N flags → 2^N notes" relationship
  already proven for single-note tremolo, generalized to accept a
  LIST of pitches per slot so both note-to-note and chord-to-chord,
  even with mismatched note counts, are handled by one function) and
  `collapse_tremolo_spanner_to_base()` (OFF-state - one sustained note/
  chord at the first-written side's pitch(es), spanning the full
  duration - given its own named function rather than an inline one-
  liner, since unlike trill this state is a real transformation, not
  a no-op).

  **Step 2 - DONE.** `realize_track_tremolo_spanner()` in
  `session.py` (same location as trill's wiring, same circular-import
  reason) wires the two pure functions to real track data: finds each
  spanner's two written sides (both appear as separate entries in a
  track's notes; processed once, via the spanner object's own
  identity, with the second side's entry dropped once absorbed into
  the result), and outputs are ALWAYS a music21 Chord - even for a
  single pitch - confirmed directly this exports identically to a
  plain Note (same note_on/note_off pair), and it avoids needing to
  switch between Note and Chord shapes depending on how many pitches
  a given slot has, which trill's deepcopy-then-mutate approach can't
  safely do when the shape itself needs to change. Velocity and
  articulations are copied from whichever original side (by
  alternation parity) each output slot corresponds to.

  `Track.get_active_notes()` now dispatches by content type rather
  than a single toggle-on/toggle-off branch: tracks labeled
  "Tremolo-" (with an interval) always compute one of the two real
  transformations regardless of toggle state, matching the
  architectural generalization flagged as needed before this step
  started; everything else keeps trill's original simpler behavior
  (off = untouched originals, on = realize). Verified this
  generalization didn't disturb trill's own behavior at all - still
  returns the literal same object when off, still realizes correctly
  when on.

  Verified thoroughly against real data: the real F6/A6 3-flag
  spanner (2 spanners total in that group) correctly collapses to 2
  sustained notes with the CORRECT inherited velocity (33 - verified
  directly against the originals, a genuinely soft passage, not a
  bug) when off, and correctly produces 16 alternating notes summing
  to the exact original total duration when on - confirmed through
  the FULL export pipeline (real note_on counts in actual MIDI
  output), not just the data layer. Chord-to-chord with mismatched
  sizes verified through the full wiring too (not just the pure
  function from step 1) - correct pitches, correct per-side velocity,
  correct alternation. Full regression clean across all three real
  files, and confirmed trill's own toggle behavior is completely
  unaffected by this generalization.

  Also added `get_tremolo_spanner_boundary()` in `parser.py` - given a
  note/chord in a spanner, determines its two sides in TEMPORAL
  (offset) order (sorted explicitly, not trusting
  `getSpannedElements()`'s own list order to already match temporal
  order), the total duration, and the flag count. Uses
  `getOffsetInHierarchy()` rather than raw `.offset` deliberately - a
  lesson already paid for once during divisi work (raw `.offset` can
  be relative to an intermediate container like a Voice, not the
  whole Part). Confirmed directly that raw `.offset` already happened
  to match the part-absolute value for every real spanner note
  checked here (none are Voice-nested, and confirmed separately that
  no real tremolo spanner in any test file crosses a measure barline
  either) - but used the hierarchy-aware method anyway, since it costs
  nothing and removes the risk entirely rather than relying on that
  holding true in general.

  Verified thoroughly: both pure functions tested in isolation
  (correct counts, correct alternation, mismatched chord sizes,
  correct duration-fit, zero/negative-duration edge cases), AND the
  full chain end to end against real data (found a real F6/A6, 3-flag,
  whole-note-duration tremolo spanner in Piccolo, correctly produced
  8 alternating notes summing to the exact original duration for ON,
  and the exact single sustained note for OFF). Full regression across
  all three real files confirmed unaffected - this step only added
  new, unused-so-far functions, no existing behavior touched yet.

  **Step 3.** Tree UI toggle - same per-row checkbox mechanism as
  trill, no separate dialog section needed (no rate to configure,
  confirmed in step 1). Renamed the shared handler from
  `on_trill_midifi_toggled` to `on_midifi_toggled`, since it's now
  generic across content types - what happens on toggle (flip the
  flag, refresh the tree) is identical regardless of which content
  type owns the row; it's `Track.get_active_notes()` that knows how
  to interpret the flag differently per type. Detection extended from
  `"Trill" in label` to also check `"Tremolo-" in label` (with the
  dash, correctly excluding bare single-note "Tremolo"). Tooltip text
  branches by content type - trill's off state needs no explanation
  (it's just untouched), but tremolo spanner's off state is ALSO a
  real transformation, so the tooltip says so explicitly rather than
  implying the checkbox does nothing when unchecked.

  **A real, serious bug found during step 3 testing, not a
  theoretical edge case - caught by testing the actual real-world
  usage pattern (toggle, export, toggle again) rather than stopping at
  "toggle once and check the result."** Confirmed directly: after a
  session had been exported even ONCE with a tremolo spanner's
  alternating (ON) realization active, the SAME original notes'
  `getSpannerSites()` no longer found their TremoloSpanner at all
  afterward - something in music21's own MIDI-writing process strips
  that bookkeeping from notes reachable from the stream being written.
  This meant toggling OFF again after having exported while ON would
  silently fall back to the ORIGINAL, un-collapsed notes (4, not the
  correct 2) - a real correctness bug that would have affected any
  user who exported even once with the toggle on, permanently breaking
  that same passage's ability to be correctly toggled again in that
  session.

  Diagnosed methodically, not by guessing: first ruled out a stale-
  widget-reference test artifact (confirmed the checkbox WAS a fresh
  object across the rebuild, so that wasn't it), then traced boundary
  detection at every single step of the sequence and found the exact
  point of divergence (present before export, gone immediately after),
  then confirmed via a control test that export WITHOUT ever touching
  the toggle leaves boundaries intact - narrowing the cause to
  something specific about the ON-state realization path interacting
  with export, not a general "export corrupts everything" issue. Also
  caught and corrected a genuine bug in my OWN test code along the way
  (a reversed `zip()` unpacking that silently produced a wrong value
  instead of an error) - initially mistaken for explaining the whole
  discrepancy, until a more carefully-written test proved the
  underlying application bug was still real regardless.

  **Fix**: stopped relying on live spanner detection at
  realization time entirely. Added
  `parser.resolve_tremolo_spanner_boundaries()`, a new parse-time pass
  (wired into `load_score()`, alongside the other resolve_* passes)
  that runs ONCE, while the live spanner/note graph is still
  guaranteed intact, and stores a fully self-contained plain dict
  directly on both of a spanner's notes - both sides' MIDI pitches,
  velocity, AND articulations (not just pitches - the same
  live-object-dependency problem would have applied to those too),
  plus total duration, flag count, and starting offset.
  `realize_track_tremolo_spanner()` rewritten to read this stored
  attribute instead of calling `get_tremolo_spanner_boundary()` live -
  ordinary Python data can't be affected by whatever export does to
  the live music21 object graph, sidestepping the whole question of
  WHY export strips that bookkeeping rather than needing to fully
  resolve music21's internal cause.

  Verified the fix directly against the exact failing sequence:
  toggle on → export (16 notes, correct) → toggle off → export (2
  notes, now correctly collapsed, previously wrongly 4) → toggle on
  again (16 notes, still correct) - confirming genuinely repeated
  cycling works, not just a one-off recovery. Re-verified the chord-
  to-chord case through the new architecture too (not just the
  original wiring), confirmed trill's own toggle is completely
  unaffected, and full regression clean across all three real files.


## Arpeggio detection

User provided a purpose-built real test file (a harp piece with
single-staff and grand-staff arpeggios, glissandos, and pedal
notation), specifically to validate detection before any realization
work started - a genuinely good call, since detection turned out to
be substantially harder than trill or tremolo spanner, both of which
could rely on music21's own object model directly.

**Root cause of the real difficulty, confirmed by reading music21's
own import source, not guessed at**: MuseScore exports every
`<arpeggiate>` element with `number="1"`, regardless of how many
distinct arpeggios actually exist in the piece. That number attribute
is exactly what the MusicXML spec uses to group simultaneous
arpeggios into one spanner - so music21, correctly following spec,
ends up merging every arpeggio in a part that shares that number into
one `ArpeggioMarkSpanner`, even across completely unrelated measures.
Confirmed directly against the user's file: one spanner incorrectly
bundled a measure-5 chord together with two distinct measure-9 events
four measures later.

Worse, found while investigating direction specifically: music21's
importer only ever applies the `direction` attribute when CREATING a
brand-new spanner for a given number - every subsequent `<arpeggiate
number="1">` in the same part just gets appended to the existing
spanner via `addSpannedElements()`, with its own direction silently
discarded. Verified this is a real, permanent data-loss, not just
hard to find: added a `direction="down"` arpeggio to a fresh test file
specifically to confirm this, and the parsed Score object had no trace
of it anywhere - not on the note, not on the spanner, nowhere.

**Fix required two real, separate workarounds, not one:**

1. **True grouping**: ignore the spanner's own (broken) element list
   entirely. Instead, cluster arpeggio-tagged notes/chords across all
   parts by (original multi-staff part identity, part-absolute
   offset) - using `getOffsetInHierarchy()` rather than raw `.offset`
   (the same measure-relative-offset trap already paid for once
   during tremolo spanner work - confirmed this file hits it too).
   Grouped by the RAW part id prefix (via a new `_split_part_id()`
   helper, parsing music21's own `"{raw_id}-Staff{N}"` split-part
   naming convention - no dedicated attribute exposes this directly,
   confirmed by checking) rather than `partName`, deliberately - two
   different instruments sharing a display name (e.g. two harps)
   could otherwise get incorrectly merged if their arpeggios happened
   to land at the same offset. Verified this reconstruction against
   the real file: correctly separates it into the true 3 events
   (1 single-staff, 2 cross-staff), not the 1 incorrectly-merged
   spanner music21's own parsing produced.

2. **True direction**: parse the raw MusicXML file directly via
   `xml.etree.ElementTree` (matching the library already used
   elsewhere in this codebase for the same reason - notation_
   preview.py's raw-XML extraction), walking each part's measures and
   notes in document order, collapsing a chord's several consecutive
   `<note>` elements (a note without `<chord/>` starts a new group,
   subsequent `<chord/>`-tagged notes belong to it) into one logical
   entry per arpeggio marking - producing an ordered, per-(raw part
   id, staff) list of directions. Correlated back to the parsed
   music21 elements POSITIONALLY: each element consumes the next
   unclaimed raw-XML direction for its own (raw part id, staff) key,
   in the same order both were encountered. This is a genuine
   assumption (that raw-XML and music21-traversal order match one-
   to-one per staff) rather than a guaranteed structural fact - but
   verified directly against the real test file rather than just
   assumed to hold, and reads as extremely likely to hold in general
   given how sequentially MusicXML and music21 both process notes.

**Architecture**: a new score-level pass,
`resolve_arpeggio_groups(score, file_path)` - the only resolve_* pass
that runs once per score rather than once per part in `load_score()`'s
pipeline, since cross-staff grouping genuinely needs to see multiple
parts at once, unlike every other pass here. Stores a fully self-
contained plain dict on each arpeggio-tagged note as
`.mididivisi_arpeggio_info` - pitches (as MIDI numbers), velocity, and
articulations captured as plain data at parse time, not left as live
object references - deliberately applying the SAME lesson tremolo
spanner already taught the hard way (a real bug where live spanner
references got silently corrupted by export), rather than waiting to
rediscover it. Runs after the per-part loop, specifically after
`apply_dynamics_to_part` has already set every note's final velocity,
so the captured velocity is correct dynamics-derived data, not a
placeholder.

Verified thoroughly against real data: the down-arp test file
correctly resolves to exactly 3 events (measure 5 single-staff →
'up', measure 9 first cross-staff event → 'up', measure 9 second
cross-staff event → 'down' - correctly recovered despite the parsing
bug), the original all-up file correctly resolves all 3 events to
'up', and - found along the way, not specifically sought out - 6 real
single-staff arpeggios in `Mysterious_Journey...musicxml` that hadn't
been noticed in any prior session, all correctly detected and
defaulting to 'up' as expected. Full regression clean across all five
real test files (the three original plus both new harp files), and
confirmed the new pass adds no meaningful overhead and doesn't affect
files with zero arpeggio content at all.

**Design decisions confirmed with the user before or during this
work, not assumed:**
- Roll rate will be exposed as delay-per-note (tempo-relative
  quarterLength), not "notes per quarter" the way trill's rate is -
  arpeggio's note count is already fixed by the chord, so there's no
  count to solve for the way trill's invented-from-nothing notes
  needed one.
- A missing direction defaults to 'up' (bottom-to-top) - explicit
  instruction, matching real notational convention.
- Curve shape (linear/log/exponential) deferred exactly like trill's
  speed shape, linear only for the MVP.
- Staggered onsets, but the whole chord rings to its ORIGINAL written
  release point - not compressed into a shorter total span the way
  trill's alternation evenly divides its total duration. A real
  design fork explicitly confirmed, not an assumption carried over
  from trill's different shape of problem.

Pure realization logic (`realize_arpeggio_notes()` in core/midifi.py)
is now done too - deliberately a different shape from trill/tremolo
spanner's "divide total duration into equal pieces": arpeggio's note
count is already fixed by the chord, so only each note's ONSET delay
needs computing, with every note still ringing to the same original
release point. Also required going back and adding `duration` to each
member's stored detection info (missed in the first pass - only
pitches/velocity/articulations were captured initially, discovered
while trying to test the realization function against real detected
data end to end, not during detection itself). Verified in isolation
(up/down sorting, exact-duplicate pitches across staves merged into
one roll-step rather than double-triggered - a real harp string can't
physically sound twice at once anyway, an aggressive roll rate
correctly dropping notes that would end up with zero/negative
duration rather than producing invalid output, zero-delay degrading
gracefully to a plain simultaneous chord) and against the real
detected down-direction cross-staff event from the test file, full
regression clean across all five real files.

**Non-destructive toggle wiring is done too.** Real architectural
question surfaced before starting: unlike trill/tremolo spanner
(single track, self-contained), a cross-staff arpeggio's two halves
live in genuinely separate Instrument objects by default (checked
directly - this app treats Harp Staff1/Staff2 as two separate
Instruments, same as divisi top/bottom, until a user merges them).
Raised this as a real design fork rather than picking silently: split
the roll correctly across both original tracks (musically ideal, real
added complexity around duplicate-pitch attribution), or have one
"primary" track (whichever staff detection encountered first,
arbitrary but deterministic) emit the full combined roll while the
other's contribution for that moment is simply dropped - since a
multi-track MIDI file plays every track simultaneously regardless of
which one holds a given note, the final audible result is identical
either way. User's actual concern was whether option 2 introduces any
destructive editing - confirmed directly it doesn't: Track.notes on
every involved track stays completely untouched regardless of which
track ends up emitting the computed output, so toggling off instantly
and exactly restores each track's own original note. Went with the
simpler option once that was confirmed.

Also discovered arpeggio-marked content had no dedicated label at
all before this step - it was just falling into whatever base
articulation label already applied (e.g. "Sustain"), unlike trill/
tremolo spanner which both get their own label. Added "Arpeggio" to
`get_note_level_label()`'s spanner-handling loop, deliberately
WITHOUT direction in the label (unlike interval for trill/tremolo
spanner, direction doesn't meaningfully change whether a passage
should be midi-fied - it's a parameter within the realization, not a
reason for different toggle behavior) and deliberately EXCLUDING
'non-arpeggio'-marked chords (a bracket instead of a squiggly line,
meaning "don't arpeggiate this one" - should just play as a normal
chord, not get grouped into a toggle that would never apply to it).

A real bug caught by reasoning through the design before testing it,
not found empirically this time: an early draft of the wiring
function computed each realized note's base offset by calling
`getOffsetInHierarchy()` live, inside the on-demand realization
function itself - the exact same live-object-dependency mistake
tremolo spanner's export-corruption bug already taught was unsafe.
Caught and fixed before ever running it: the offset is now captured
once as plain data during detection (parser.resolve_arpeggio_groups
already computes it for grouping purposes) and simply read back later,
with zero dependency on the note still being correctly attached to
its original stream by the time the toggle actually gets used.

`MidifiConfig` gained `arpeggio_delay_per_note` (default 0.125, a
32nd note - tempo-relative, matching trill's own rate philosophy),
following the exact same from_dict fallback reasoning already
established for trill's rate (safe to match the live default, since
the toggle is per-note and on-demand, not session-wide and always-
applied the way tremolo's threshold is).

Verified end to end against real data: toggle off correctly returns
untouched originals on both tracks (zero-cost, literal same objects);
toggle on correctly shows the primary track (Staff1) absorbing the
full combined roll (10 notes total across all three real arpeggio
events, in the exact case-by-case order the pure function already
proved correct - ascending for the two 'up' events, descending for
the 'down' one) while the secondary track (Staff2) correctly emits
nothing for that same moment. Confirmed through the actual export
pipeline too, not just the data layer - both toggle states produce
the correct real MIDI note_on counts. Re-verified trill is completely
unaffected by the shared dispatch changes. Full regression clean
across all five real test files.

The tree UI toggle is the only remaining piece, not yet built.

## Arpeggio - DONE

Built in the same staged shape as trill/tremolo spanner (detection →
pure realization → toggle wiring → tree UI toggle), each step fully
tested before the next began - the full step-by-step history,
including the real MuseScore export bugs found and fixed along the
way, is captured in the sections above (arpeggio detection, and the
"non-destructive toggle wiring is done too" continuation). Summary of
what shipped and the design decisions confirmed along the way:

- **Arpeggio - fully done, including the tree UI toggle.** No sample
  library has an "arpeggio patch" -
  needs to become real staggered note-on events, same non-destructive
  toggle architecture as trill/tremolo spanner. Roll rate exposed as
  delay-per-note (tempo-relative quarterLength, not "notes per
  quarter" like trill - arpeggio's note count is already fixed by the
  chord, so there's no count to solve for the way trill has). Curve
  shape (linear/log/exponential) deferred exactly like trill's speed
  shape - linear only for now. Confirmed design: staggered onsets, but
  the WHOLE chord still rings to its original written release point
  (not compressed into a shorter span the way trill's alternation
  divides duration evenly) - `realize_arpeggio_notes()` in
  `core/midifi.py` implements exactly this, verified in isolation
  (up/down sorting, exact-duplicate pitches across staves correctly
  merged into one roll-step rather than double-triggered, an
  aggressive roll rate correctly dropping notes that would have zero/
  negative duration rather than producing invalid output) and against
  real detected data end to end (the real down-direction cross-staff
  event from the test file, all notes correctly ringing to the exact
  same original release point). Full detail in DEVLOG.md.

  **Detection - DONE, and genuinely harder than trill/tremolo spanner
  turned out to be**, due to a real MuseScore export quirk (not
  music21's fault, and not hypothetical - confirmed directly against
  real files): every `<arpeggiate>` element exports with the same
  "number" attribute regardless of how many distinct arpeggios exist,
  which makes music21 both (a) incorrectly merge unrelated arpeggios
  across different measures into one spanner object, and (b) silently
  discard direction data for every arpeggio after the first in a part
  (confirmed in music21's own source - direction is only ever applied
  when a NEW spanner is created, never when an existing one is reused).
  Both fixed in a new score-level pass (`resolve_arpeggio_groups`,
  the only resolve_* pass that runs once per score rather than once
  per part - genuinely needs to see multiple parts at once for cross-
  staff grouping): TRUE groups reconstructed by clustering arpeggio-
  tagged notes/chords sharing the same part-absolute offset within the
  same original multi-staff part (not partName, which could wrongly
  merge two same-named instruments); direction recovered by reading
  the raw XML directly and correlating it back positionally. Verified
  against real data throughout, including a purpose-built test file
  (`Harp_Test_-_down_arp.musicxml`) confirming a genuine cross-staff,
  explicit-down-direction arpeggio is detected correctly, and 6 real
  single-staff arpeggios found in `Mysterious_Journey...musicxml` that
  hadn't been noticed before this work.

  **Final step - tree UI toggle and rate exposure.** Same per-row
  checkbox mechanism as trill/tremolo spanner, extended to a third
  content type via a three-way tooltip branch (trill and arpeggio's
  off state needs no explanation - both are genuinely untouched;
  tremolo spanner's off state is a real transformation and the
  tooltip says so). Unlike tremolo spanner, arpeggio DOES have a real
  exposed rate (the delay-per-note), so it also got its own section in
  the Midi-fy dialog, mirroring trill's rate control exactly -
  confirmed directly that changing it applies instantly with no
  rebuild warning, matching trill's rate and NOT tremolo's threshold.
  Verified the complete toggle cycle through real UI clicks end to
  end, correctly handling the stale-widget-reference risk from
  `refresh_tree()` rebuilding the tree on every toggle (a lesson
  already learned once for trill, applied here without needing to
  rediscover it): both harp instances' checkboxes clicked on, correctly
  producing the full 10-note combined roll on the surviving track;
  clicked back off, correctly restoring the original 2-track, 10-note
  split. Full regression clean across all five real test files.

## Merged-group Midi-fy checkbox bug

Real bug reported after actually using the shipped arpeggio feature:
after merging a grand-staff Harp's two instruments together (Merge or
Auto Merge, a routine, expected workflow for exactly this kind of
instrument), the Arpeggio checkbox disappeared entirely, with no way
left to toggle it.

Root cause: the checkbox visibility check had required
`not group.is_merged` since trill's very first implementation of this
UI - a restriction that had always existed, silently carried forward
unquestioned through tremolo spanner and arpeggio's own builds. Rather
than assume why it was there, checked directly what merging actually
does: confirmed `merge_instruments()` combines matching-label groups
together (both instrument's "Arpeggio" groups become ONE group with
two same-labeled tracks, not two differently-labeled ones bundled
together) - meaning the ambiguity the restriction was presumably
guarding against (what should one checkbox control if a merged group
holds several DIFFERENT labels) never actually applied to this real
case. The restriction was simply too broad, hiding the checkbox for
an unambiguous case along with the genuinely ambiguous one it may have
been written for.

Fixed by replacing the `not group.is_merged` check with "do ALL tracks
in this group share the same midi-fy-eligible label" - true regardless
of merge status, and only ever false for the genuinely ambiguous case.
`on_midifi_toggled()` now takes a LIST of tracks rather than a single
one (an unmerged group just passes its own one-element list, so this
is one code path for both cases), toggling every track in the group
together. Checkbox state reflects "are ALL tracks currently on" -
deliberately not a three-state partial indicator, which would be more
precise for a mixed state but adds real complexity for something that
shouldn't come up often in practice.

Verified directly against the real harp file: checkbox correctly
REMAINS present after merging both Harp instances (the exact bug
being fixed), clicking it correctly toggles both underlying tracks
together (confirmed via track state, not just the checkbox's own
visual state), and the full export correctly reflects the toggled
merged roll (10 notes, matching the pre-merge realized total exactly).
Re-verified trill's original single-track, unmerged case still works
unaffected. Full regression clean across all five real test files.

## Arpeggio redesign - removed per-track checkbox and label entirely

The merged-group checkbox fix above turned out to be treating a
symptom, not the disease. User reported the real underlying problem
after using the shipped feature further: arpeggio content ALSO needs
to merge cleanly with a NEIGHBORING different-labeled group (e.g. an
arpeggio passage merging with a "Sustain" group it's musically part
of) - not just with another arpeggio-labeled group, which is what the
earlier fix actually solved. A checkbox tied to a dedicated "Arpeggio"
label has no coherent meaning once that label's group merges with a
genuinely different one.

First proposal (moving arpeggio to tremolo's parse-time, destructive
architecture) was flatly - and correctly - rejected: this project has
been explicit throughout about staying non-destructive, and the user
directly pointed back at an EARLIER conversation (before any of the
midi-fy toggle infrastructure existed) where retrofitting tremolo onto
trill's non-destructive model was discussed and deliberately deferred,
not abandoned. Proposing to move arpeggio backward onto tremolo's
model was the wrong direction entirely.

The actual fix, once framed correctly: arpeggio never needed its own
label or group in the first place. The label existed ONLY to make
per-row checkbox detection possible. Given the user's own separately-
confirmed premise (no sample library has a dedicated arpeggio patch,
unlike trill's timpani-style rolls or tremolo spanner's 3rd-interval
patches), a per-track opt-out was never buying anything real - the
decision is the same everywhere. Removing the "Arpeggio" label
entirely means arpeggio-marked notes just stay within whatever group
their base articulation already belongs to (e.g. "Sustain") from the
moment Session.from_score() runs - there is no separate group left to
ever need merging, by construction, rather than by a merge-time fix.

Confirmed `merge_midifi_variants()` (tremolo's existing merge-back
mechanism) was NOT needed here and would have been the wrong tool -
that mechanism is for merging an ALREADY-SEPARATE "Midifi+X" group
back into "X" after the fact; removing the arpeggio label avoids ever
creating that separate group at all.

**Architecture**: `Track.get_active_notes()` restructured so arpeggio
is applied as an ADDITIONAL pass chained after whatever the label-
based dispatch (trill/tremolo spanner) already produced, rather than
being one branch of a single either/or dispatch - gated by a new
global `MidifiConfig.arpeggio_enabled` flag, not a per-track
`midifi_toggle_active` check. `realize_track_arpeggio()` was already
safe to call this way without modification - it only ever touches
notes actually carrying `mididivisi_arpeggio_info`, passing everything
else through untouched, so chaining it after any other realization is
always correct regardless of what that produced. Crucially, this
KEEPS the on-demand, computed-fresh-every-call architecture - both the
enable flag and the roll rate stay instantly adjustable, no rebuild
needed, unlike tremolo's threshold. The per-row checkbox for arpeggio
was removed from the tree entirely; the Midi-fy dialog gained a
plain "Enable arpeggio midi-fy" checkbox alongside the existing rate
control, confirmed neither triggers the rebuild-warning path.

**A real, separate bug found and fixed while touching this code, not
part of the redesign itself**: `_extract_arpeggio_directions_from_xml`
never actually checked for `<non-arpeggiate>` - a genuinely different
MusicXML element (not an `<arpeggiate>` with some direction value)
used to mark a chord that should explicitly NOT be rolled, in contrast
to surrounding chords that should. None of the real test files used so
far happen to contain one, which is exactly why this went unnoticed
until now. The exclusion check that referenced this ('non-arpeggio')
existed in the code already, but could never actually fire, since
nothing ever produced that value. Fixed by detecting `<non-
arpeggiate>` directly alongside `<arpeggiate>`, and moved the actual
exclusion check from the (now-deleted) labeling step into
`realize_track_arpeggio` itself, where the real decision now lives.
Verified with a purpose-built synthetic file, since no real test file
exercises this.

Verified thoroughly, including two real test-methodology traps caught
and corrected before reporting anything as broken: an early check
compared total `note_on` counts before/after enabling arpeggio and
found them unexpectedly equal for the harp file - traced directly
(not assumed) to a coincidental cancellation, where one track's gain
from becoming the cross-staff primary exactly matched the other
track's loss from becoming secondary; confirmed this was correct
behavior, not a bug, by checking actual pitch content and per-track
distribution instead of the misleading summed total. A second,
similar false alarm on a different real file (`Mysterious_
Journey...musicxml`, single-staff arpeggios only) - total count
staying IDENTICAL turned out to be simply correct: realizing a chord
into a staggered roll doesn't add notes, it only changes their onset
timing, so an unchanged note count was actually the right result -
confirmed by checking real onset offsets directly (a plain chord's
notes sharing one offset vs. the realized version's five staggered
offsets), not by continuing to assert on note count.

Final verification confirmed: arpeggio-marked notes correctly stay
inside "Sustain" from parse time (no "Harp - Arpeggio" group exists
at all anymore); the global flag correctly gates realization on/off,
instantly, for both the harp test file and a real orchestral file
with different (single-staff) arpeggio content; merging is now a
complete non-issue (checked directly, both before and after merging
the two harp instruments, confirmed realization behaves identically
either way, since there was never a separate group to be affected by
merging); the dialog's new checkbox correctly applies instantly with
no rebuild warning; trill's own checkbox mechanism is completely
unaffected. Full regression clean across all five real test files.

## Arpeggio - restoring the separate Midifi+ track (correcting a misread intent)

The previous redesign entry above solved a real problem (per-track
checkbox breaking on merge) but solved it by removing MORE than was
actually asked for. User corrected this directly and firmly: "treat
this like tremolo" meant literally, from the UI perspective - keep
arpeggio-marked notes in their own separate, visible track (matching
tremolo's own "Midifi+X" labeling convention exactly), make it
mergeable via the existing "Merge Midi-fy" button or a regular manual
merge, and let the user decide whether to merge it - not remove the
separate track and fold arpeggio invisibly into its base articulation
group, which is what actually got built. Worth being honest about:
this was a real misread of "treat this like tremolo" as being about
the underlying MODEL (which the user was NOT asking to copy) rather
than the UI SHAPE (a separate, mergeable track) they specifically
meant.

While confirming the fix, user also corrected a second, longer-
standing misunderstanding: tremolo's current destructive, parse-time
model was never intended to be permanent. It was explicitly deferred -
not abandoned - during the very first trill design conversation,
specifically so the non-destructive pattern could be proven once on
trill before migrating an already-working feature. That deferral had
apparently been re-explained by the user multiple times since without
ever landing as a clear, standalone commitment - it only ever existed
as buried context in prior devlog entries, never as its own backlog
item. Added one directly this time (see BACKLOG.md's "Midi-fy
features" section) rather than let this keep needing to be re-raised.

**The actual fix**: reused the EXACT existing `mididivisi_midifi_source`
marker mechanism tremolo already uses for its own "Midifi+X" labeling
(confirmed directly it's only ever checked for presence, never a
specific value, so safe to set to "arpeggio" instead of "tremolo") -
set only on the PRIMARY member of each arpeggio event in
`resolve_arpeggio_groups` (parser.py), deliberately not on secondary
members (a cross-staff event's non-primary track never produces its
own realized output, so labeling it "Midifi+X" too would be
misleading), and deliberately not on 'non-arpeggio'-marked chords
(which will never be realized regardless of the global setting, so
should never carry a "will be realized" label). No new labeling logic
was needed at all - `get_note_level_label()`'s existing
`mididivisi_midifi_source` check already handles the prefixing
correctly once the marker is set on the right notes.

One real semantic difference from tremolo worth being explicit about,
raised proactively rather than discovered later: tremolo's own use of
"Midifi+X" means the note has ALREADY been destructively realized by
the time that label exists - the transformation already happened at
parse time. Arpeggio's use of the same label means something subtly
different: the note WILL BE realized if the global
`arpeggio_enabled` setting is on - the underlying note stays
completely untouched, computed fresh on demand exactly like trill,
regardless of what its current label says. Confirmed with the user
this difference is fine and intentional, not something to paper over -
it's really tremolo's OWN meaning that's the outlier here, once
tremolo itself gets migrated to match this same non-destructive
pattern.

Verified thoroughly against real data: the separate "Harp - Midifi+
Sustain" track is back (3 notes on the primary instance, all 3 real
arpeggio events on this file correctly attributed to Staff1 as
primary); the secondary instance's "Sustain" correctly still contains
all 43 of its own notes, including its 2 secondary-member arpeggio
notes, unlabeled as intended; `Session.merge_midifi_variants()` (the
existing "Merge Midi-fy" mechanism, confirmed generic and unmodified)
correctly merges "Midifi+Sustain" into "Sustain"; realization still
correctly works after that merge (same note counts already verified
correct in earlier testing); a regular manual merge (selecting both
groups directly, not using the Merge Midi-fy button) also works
correctly, confirming this isn't tied to one specific merge mechanism.
Re-verified the other real file with arpeggios (`Mysterious_
Journey...musicxml`, single-staff only) correctly shows its own
"Midifi+Sustain" track. Trill's own checkbox mechanism confirmed
completely unaffected. Full regression clean across all five real
test files.
