"""Optional deterministic ReportLab report preparation, outside ordinary builds.

Run with the bundled document Python (or install reportlab). Commit the prepared
PDF and receipt together; static builds only verify and copy these bytes.
"""
from __future__ import annotations

import argparse
import io
from pathlib import Path
import xml.sax.saxutils

try:
    from research_citations import ROOT, context_digest, json_bytes, privacy_filter, publication_metadata, sha256
except ImportError:
    from scripts.research_citations import ROOT, context_digest, json_bytes, privacy_filter, publication_metadata, sha256


def render_report_pdf(context):
    try:
        import reportlab
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.pdfgen.canvas import Canvas
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, KeepTogether
    except ImportError:
        raise RuntimeError("PDF preparation requires the optional ReportLab dependency; ordinary static builds do not.") from None
    report = privacy_filter(context["report"])
    metadata = publication_metadata(context)
    font_dir = Path(reportlab.__file__).parent / "fonts"
    for name, filename in (("ResearchVera", "Vera.ttf"), ("ResearchVeraBold", "VeraBd.ttf")):
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(font_dir / filename)))
    styles = getSampleStyleSheet()
    for name in ("BodyText", "Normal", "Heading1", "Heading2", "Title"):
        styles[name].fontName = "ResearchVeraBold" if name in ("Heading1", "Heading2", "Title") else "ResearchVera"
        styles[name].textColor = colors.HexColor("#18312c")
    styles["BodyText"].fontSize, styles["BodyText"].leading = 10, 15
    styles["BodyText"].spaceAfter = 9
    styles["Title"].fontSize, styles["Title"].leading = 25, 32
    styles["Title"].alignment = TA_LEFT
    styles["Heading2"].spaceBefore, styles["Heading2"].spaceAfter = 19, 9
    styles["Heading2"].keepWithNext = True
    styles.add(ParagraphStyle("Evidence", fontName="ResearchVera", fontSize=8, leading=12,
                              textColor=colors.HexColor("#52665e"), spaceAfter=12))
    escape = lambda text: xml.sax.saxutils.escape(str(text)).replace("\n", "<br/>")
    story = [Paragraph(escape(report["title"]), styles["Title"]), Spacer(1, 12),
             Paragraph(escape(metadata["status"].upper() + " | " + report["release_id"] + " | Updated " + report["updated_on"]), styles["Evidence"]),
             Paragraph(escape(metadata["note"]), styles["BodyText"]),
             Paragraph("Readiness and limitations", styles["Heading2"])]
    for reason in context["gate"].get("reasons", []):
        story.append(Paragraph(escape(reason), styles["BodyText"]))
    story.append(Paragraph("Coverage", styles["Heading2"]))
    def coverage_lines(value, prefix=""):
        if isinstance(value, dict):
            for key, item in sorted(value.items()):
                yield from coverage_lines(item, prefix + (" / " if prefix else "") + key)
        else:
            yield prefix + ": " + str(value)
    for line in coverage_lines(context["gate"].get("coverage", {})):
        story.append(Paragraph(escape(line), styles["Evidence"]))
    for section in report.get("sections", []):
        heading = Paragraph(escape(section["title"]), styles["Heading2"])
        for index, paragraph in enumerate(section.get("paragraphs", [])):
            group = ([heading] if index == 0 else []) + [Paragraph("<b>" + escape(paragraph.get("kind", "analysis")) + ":</b> " + escape(paragraph["text"]), styles["BodyText"])]
            if paragraph.get("claim_ids"):
                group.append(Paragraph("Evidence IDs: " + escape(", ".join(paragraph["claim_ids"])), styles["Evidence"]))
            story.append(KeepTogether(group))
        if not section.get("paragraphs"):
            story.append(heading)
    story.extend([Paragraph("Evidence and reproduction", styles["Heading2"]),
        Paragraph("The complete public evidence graph accompanies this report in the offline archive. Paragraph evidence IDs refer to that graph. The JSON, CSV and SQLite contain equivalent privacy-filtered projection " + metadata["projection_version"] + ". Canonical dataset 2.5.0 remains unchanged outside this archive. Raw source text and personal contact details are excluded.", styles["BodyText"]),
        Paragraph("Verify the archive with MANIFEST.json. Reproduce with the source repository's scripts/build_public_snapshot.py. Owned research and text use CC BY 4.0; third-party material retains its rights. Review scope and research gaps remain explicit. This PDF's status does not establish website or external mirror publication.", styles["BodyText"])])
    stream = io.BytesIO()
    document = SimpleDocTemplate(stream, pagesize=(612, 792), rightMargin=54, leftMargin=54,
                                 topMargin=51, bottomMargin=54, title=report["title"], author=metadata["author"], allowSplitting=1)
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("ResearchVera", 8)
        canvas.setFillColor(colors.HexColor("#52665e"))
        canvas.drawString(54, 31, "ScienceToStartup | " + metadata["status"] + " | " + report["release_id"])
        canvas.drawRightString(558, 31, str(doc.page))
        canvas.restoreState()
    def deterministic_canvas(*args, **kwargs):
        kwargs["invariant"] = 1
        kwargs["pageCompression"] = 1
        return Canvas(*args, **kwargs)
    document.build(story, onFirstPage=footer, onLaterPages=footer, canvasmaker=deterministic_canvas)
    return stream.getvalue()


def prepare_report_pdf(context, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    blob = render_report_pdf(context)
    (output / "report.pdf").write_bytes(blob)
    receipt = {"schema_version": 1, "context_sha256": context_digest(context), "sha256": sha256(blob),
               "release_id": context["report"]["release_id"], "renderer": "ReportLab with embedded Bitstream Vera",
               "verification": "Rendering and text inspection are required before archival publication."}
    (output / "report-pdf.json").write_bytes(json_bytes(receipt))
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "data/research")
    args = parser.parse_args()
    from research_report import build_context
    receipt = prepare_report_pdf(build_context(), args.output)
    print("Prepared PDF " + receipt["sha256"] + "; render and inspect before publication.")


if __name__ == "__main__":
    main()
