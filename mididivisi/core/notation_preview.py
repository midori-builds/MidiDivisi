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


_TEXT_LABEL_PATTERN = re.compile(
    r'(<text[^>]*?)font-size="0px"([^>]*>)\s*'
    r'(?:<tspan(?![^>]*font-size)[^>]*>\s*)+'
    r'<tspan[^>]*font-size="(\d+px)"[^>]*>(.*?)</tspan>\s*'
    r"(?:</tspan>\s*)+</text>",
    re.DOTALL,
)


def _flatten_text_labels(svg):
    """Flatten Verovio's "<text font-size=0px> wrapping one or more
    plain <tspan> layers, ending in one real <tspan font-size=Npx>
    CONTENT</tspan>" pattern (zero out the parent, size everything via
    nested tspans) into a single <text font-size="Npx">CONTENT</text>.

    The number of wrapper levels varies by content type - confirmed
    directly, not assumed: instrument names/measure numbers use 2
    levels, but text directions (e.g. "mute") use 3 (an extra
    class="rend" wrapper) - so this matches an arbitrary number of
    wrapper levels generically rather than a hardcoded count, which
    is what a first version (assuming exactly 2 levels always) missed
    for one specific real case.

    This is what was causing instrument names, measure numbers, and
    text directions to go missing - the nested-svg fix above resolved
    the actual notation being blank, but text labels specifically use
    this SEPARATE pattern, triggering a different set of Qt warnings
    ("Point size <= 0", "Could not add child element to parent
    element") - confirmed by finding every warning's exact source
    line and seeing all of them were this structure.
    """
    return _TEXT_LABEL_PATTERN.sub(r'\1font-size="\3"\2\4</text>', svg)


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
