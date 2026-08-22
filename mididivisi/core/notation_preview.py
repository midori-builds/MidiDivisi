"""
Notation preview (crude v1).

Renders a single instrument's REAL notation, extracted directly from
the original MusicXML file - deliberately NOT reconstructed from our
own internal Track/Group note data, which is just flat offset/
duration/pitch lists with no measure/voice/beaming structure at all.
Pulling one <part> out of the real, original file gives correct clefs,
key/time signatures, barring, and beaming for free, since none of it
is invented by us - see the design discussion in BACKLOG.md's
"Notation preview" section for why this was chosen over trying to
render from our own data.

Uses Verovio (https://verovio.org, `pip install verovio`) to render
MusicXML directly to SVG - confirmed via testing to be a real, current,
Python-native library (no browser/web engine needed).
"""

import re
import xml.etree.ElementTree as ET

import verovio


def extract_part_xml(original_file_path, target_natural_key):
    """Extract ONE instrument's <part> from the original MusicXML file
    as a standalone, minimal, valid MusicXML document (string).

    target_natural_key is InstrumentIdentity.natural_key -
    (original_name, occurrence_index, variant). Only the first two
    elements are used for matching here - `variant` (None for a
    normal identity, or "DivisiTop"/"DivisiBottom"/"Solo" for a
    synthesized one - see session.py) is deliberately IGNORED: a
    Divisi/Solo-derived instrument doesn't correspond to a separate
    <part> in the original file at all, since the split happens
    within our own parsing, not in the source notation. Previewing
    one just shows the SAME underlying original part - genuinely
    correct, not a compromise, since the notation software's own
    rendering shows these distinctions WITHIN one staff (voices, or a
    "solo"/"div." text direction), not as separate staves.

    Operates on the RAW XML directly (not via a music21 parse-and-
    rewrite round trip) - more faithful to the original notation,
    since music21's own MusicXML writer doesn't necessarily preserve
    every engraving-level detail of the source file exactly.

    Drops <part-group>, <credit>, <work>, and <identification> from
    the extracted document (page-specific credit text and part
    brackets don't make sense for a single extracted part, and
    aren't needed for rendering the notation itself) - keeps
    <part-list> (trimmed to the one matching <score-part>), <defaults>
    if present, and the matching <part> element completely unchanged.
    """
    target_name, target_occurrence = target_natural_key[0], target_natural_key[1]

    tree = ET.parse(original_file_path)
    root = tree.getroot()

    part_list = root.find("part-list")
    score_parts = part_list.findall("score-part")

    occurrence_counts = {}
    matching_part_id = None
    matching_score_part = None

    for score_part in score_parts:
        name_el = score_part.find("part-name")
        name = name_el.text if name_el is not None else "(unnamed part)"
        occurrence = occurrence_counts.get(name, 0)
        occurrence_counts[name] = occurrence + 1

        if name == target_name and occurrence == target_occurrence:
            matching_part_id = score_part.get("id")
            matching_score_part = score_part
            break

    if matching_part_id is None:
        # No exact occurrence match, most likely a grand-staff
        # instrument (Harp, Piano, etc.) - the RAW XML often has only
        # ONE <part> internally declaring 2 staves (e.g.
        # <staves>2</staves>), which music21 auto-splits into two
        # separate Part objects DURING ITS OWN parsing - meaning our
        # natural_key/occurrence_index system (built from music21's
        # already-split parts) and this raw-XML-based extraction
        # (which only ever sees ONE real <part> declaration for such
        # an instrument) are counting two structurally different
        # things. Confirmed directly against a real file - verified
        # via inspecting the raw part-list, not assumed. Known
        # limitation for this crude v1: falls back to matching by
        # name alone and returning the FULL raw part (both staves
        # together) - not yet able to cleanly extract just one half
        # of a grand-staff instrument. Both "occurrences" of such an
        # instrument will show the same combined notation until this
        # is addressed properly.
        for score_part in score_parts:
            name_el = score_part.find("part-name")
            name = name_el.text if name_el is not None else "(unnamed part)"
            if name == target_name:
                matching_part_id = score_part.get("id")
                matching_score_part = score_part
                break

    if matching_part_id is None:
        raise ValueError(
            f"Could not find part matching {target_natural_key} in {original_file_path}"
        )

    matching_part = None
    for part_el in root.findall("part"):
        if part_el.get("id") == matching_part_id:
            matching_part = part_el
            break

    if matching_part is None:
        raise ValueError(
            f"Found score-part id {matching_part_id!r} but no matching <part> element"
        )

    new_root = ET.Element("score-partwise", {"version": root.get("version", "4.0")})

    defaults = root.find("defaults")
    if defaults is not None:
        new_root.append(defaults)

    new_part_list = ET.SubElement(new_root, "part-list")
    new_part_list.append(matching_score_part)

    new_root.append(matching_part)

    xml_declaration = '<?xml version="1.0" encoding="UTF-8"?>\n'
    doctype = (
        '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML '
        '4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">\n'
    )
    return xml_declaration + doctype + ET.tostring(new_root, encoding="unicode")


def render_musicxml_to_svg_pages(musicxml_string):
    """Render a MusicXML string to a list of SVG page strings (one
    entry per page) via Verovio, post-processed for Qt's SVG renderer.

    Verovio's raw output nests ALL the actual musical content (staves,
    noteheads, everything) inside a SECOND, inner <svg viewBox="...">
    element used purely to establish a scaled coordinate system - the
    outer <svg> is essentially an empty wrapper. Qt's SVG renderer
    (SVG Tiny 1.2 profile) silently discards any nested <svg> element
    entirely, which meant the preview window rendered as a correctly-
    sized but completely BLANK page - confirmed directly (not assumed)
    by inspecting Verovio's actual raw output and finding exactly this
    nested structure, then verifying the fix's scale-factor math
    against real output before relying on it.

    Fixed by converting every non-outermost <svg> tag into an
    equivalent <g transform="scale(...)"> - which Qt handles fine,
    nested groups are completely ordinary SVG - computing the correct
    scale from that inner element's own viewBox relative to whatever
    the current effective canvas size is, rather than hardcoding a
    fixed factor (verified as 0.1 for a real page, but not assumed to
    always be exactly that for every rendered page/piece).
    """
    tk = verovio.toolkit()
    loaded = tk.loadData(musicxml_string)
    if not loaded:
        raise ValueError("Verovio could not load the provided MusicXML data")

    page_count = tk.getPageCount()
    raw_pages = [tk.renderToSVG(page) for page in range(1, page_count + 1)]
    return [_flatten_text_labels(_flatten_nested_svg(svg)) for svg in raw_pages]


SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
ET.register_namespace("", SVG_NS)  # keeps output tags unprefixed ("svg", not "ns0:svg") - Qt's renderer expects plain SVG tag names
# A real bug this specifically fixes, found via the user's screenshot
# after the previous fix shipped, not caught before then: WITHOUT this
# registration, ElementTree auto-generates a generic prefix (ns1, ns2,
# ...) for any namespace it encounters that hasn't been registered -
# turning every xlink:href attribute into something like ns1:href on
# serialization. Verovio uses xlink:href on <use> elements for EVERY
# glyph (noteheads, clefs, rests, dynamics, time/key signatures - all
# of it), so this one omission silently broke every single glyph
# reference at once, while raw path/line content (beams, slurs, tempo
# text) kept rendering fine - exactly matching what the screenshot
# showed. The "link # is undefined!" warning noted as a separate,
# lower-priority cosmetic issue in the previous fix was actually THIS
# same bug, just manifesting as a warning instead of an outright
# missing symbol for whichever instrument happened to be tested then -
# should have been chased down immediately instead of set aside.
ET.register_namespace("xlink", XLINK_NS)


def _flatten_text_labels(svg):
    """Flatten Verovio's "<text font-size=0px> wrapping one or more
    plain <tspan> layers, ending in one or more real
    <tspan font-size=Npx>CONTENT</tspan> runs" pattern (zero out the
    parent, size everything via nested tspans) into a
    <text font-size="Npx"> with those real tspans as DIRECT children.

    Rewritten to operate on the parsed XML TREE rather than a regex
    over the raw text - a real, found-not-assumed bug in an earlier
    regex-based version: it correctly handled a SINGLE run of nested
    wrapper tspans, but a tempo marking ("Andante moderato") turned
    out to have TWO SIBLING wrapper groups within the same outer
    <text> element (multiple differently-styled runs, not one) - a
    genuinely different tree shape a regex can't reliably distinguish
    from "this <text> element is now complete" while scanning linear
    text. The regex matched partway through the first run's closing
    tags, mistaking them for the final </text>, and left the second
    run and the REAL closing tag orphaned - producing literally
    malformed XML (a <text> opening tag closed by </tspan>) that Qt's
    SVG parser rejected outright, silently falling back to a tiny
    default widget size - which is what actually caused certain
    instruments' previews to appear to show nothing at all. A tree-
    based approach sidesteps the whole class of bug: correctly finds
    ALL real-content tspans (any font-size other than 0px) as
    descendants of a font-size=0px <text>, however many sibling runs
    there are, since parent/child/sibling relationships are read from
    the actual tree structure rather than inferred from text pattern
    matching.

    Each real-content tspan becomes a direct child of the flattened
    <text> element, keeping its own font-size - preserving multi-run
    styling rather than collapsing everything into one merged string
    with only the first run's size.
    """
    root = ET.fromstring(svg)
    text_tag = f"{{{SVG_NS}}}text"
    tspan_tag = f"{{{SVG_NS}}}tspan"

    for text_el in root.iter(text_tag):
        if text_el.get("font-size") != "0px":
            continue

        real_content_tspans = [
            el for el in text_el.iter(tspan_tag)
            if el.get("font-size") not in (None, "0px") and (el.text or "").strip()
        ]
        if not real_content_tspans:
            continue  # doesn't match the expected wrapper shape - leave untouched rather than guess

        text_el.set("font-size", real_content_tspans[0].get("font-size"))
        for child in list(text_el):
            text_el.remove(child)
        text_el.text = None
        for tspan in real_content_tspans:
            # A real, separate bug found via a screenshot after the
            # first version of this fix shipped: only font-size was
            # being copied here, silently dropping every other
            # attribute - including font-family, which for Verovio's
            # music-glyph tspans (e.g. a metronome mark's note symbol,
            # rendered as a private-use-area character in a dedicated
            # "Leipzig" glyph font) is what actually maps that
            # character to a visible symbol at all. Without it, the
            # character survives in the output (confirmed directly -
            # this was never actually a content-loss bug) but renders
            # as an empty/missing glyph in whatever the ambient font
            # is, which has no mapping for that private-use codepoint
            # - visible in the screenshot as a solid black placeholder
            # box instead of the quarter-note symbol. Copying every
            # attribute rather than reconstructing just the one this
            # was tested against is what actually generalizes
            # correctly, the same lesson the tree-based rewrite itself
            # was already meant to teach.
            flat_tspan = ET.SubElement(text_el, tspan_tag, dict(tspan.attrib))
            flat_tspan.text = tspan.text

    return ET.tostring(root, encoding="unicode")


def _flatten_nested_svg(svg):
    """Convert every <svg> tag that ISN'T the first (outermost) one
    into an equivalent <g transform="scale(...)"> element, preserving
    its content. See render_musicxml_to_svg_pages for why this is
    needed. Falls back to returning the SVG unmodified if the
    structure doesn't match what's expected, rather than raising -
    a slightly-imperfect render is a much better failure mode here
    than the whole preview window crashing.
    """
    svg_tags = list(re.finditer(r"<svg\b([^>]*)>", svg))
    if len(svg_tags) < 2:
        return svg  # nothing nested - already fine as-is

    # Track the "current" effective canvas size as we walk outward to
    # inward, so a THIRD level of nesting (if it ever occurs) computes
    # its scale relative to the SECOND level's size, not always the
    # outermost - correct even if Verovio's structure changes in a
    # future version.
    outer_attrs = svg_tags[0].group(1)
    canvas_w, canvas_h = _extract_size(outer_attrs)

    result = svg
    # Process from the LAST match backward, so replacing text doesn't
    # shift the character offsets of matches not yet processed.
    for match in reversed(svg_tags[1:]):
        attrs = match.group(1)
        view_box = re.search(r'viewBox="([\d.\s-]+)"', attrs)

        if view_box is None or canvas_w is None or canvas_h is None:
            continue  # can't safely compute a transform - leave this one as-is

        minx, miny, vb_w, vb_h = (float(v) for v in view_box.group(1).split())
        scale_x = canvas_w / vb_w if vb_w else 1.0
        scale_y = canvas_h / vb_h if vb_h else 1.0

        transform = f"translate({-minx * scale_x},{-miny * scale_y}) scale({scale_x},{scale_y})"

        # Preserve any other attributes (class, color, font-family,
        # etc.) except viewBox/width/height, which don't apply to <g>.
        kept_attrs = re.sub(r'\s*(viewBox|width|height)="[^"]*"', "", attrs)
        replacement_open = f"<g{kept_attrs} transform=\"{transform}\">"

        start, end = match.span()
        result = result[:start] + replacement_open + result[end:]

        # This inner element's own size becomes the canvas for
        # anything nested WITHIN it, in case of a third level.
        canvas_w, canvas_h = vb_w, vb_h

    # Close tags: replace the LAST N-1 </svg> occurrences (the
    # innermost ones) with </g> - the very first </svg> in the
    # document is the true outer closing tag and must stay as-is.
    closing_positions = [m.start() for m in re.finditer(r"</svg>", result)]
    for pos in reversed(closing_positions[:-1]):
        result = result[:pos] + "</g>" + result[pos + len("</svg>") :]

    return result


def _extract_size(svg_attrs_string):
    """Pull a usable (width, height) in user units from an <svg>
    tag's attribute string - prefers its own viewBox (exact user-unit
    span) and falls back to width/height in px if no viewBox is
    present. Returns (None, None) if neither is found.
    """
    view_box = re.search(r'viewBox="([\d.\s-]+)"', svg_attrs_string)
    if view_box is not None:
        _, _, w, h = (float(v) for v in view_box.group(1).split())
        return w, h

    width = re.search(r'width="([\d.]+)', svg_attrs_string)
    height = re.search(r'height="([\d.]+)', svg_attrs_string)
    if width is not None and height is not None:
        return float(width.group(1)), float(height.group(1))

    return None, None
