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
