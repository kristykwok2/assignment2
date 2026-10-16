"""Build the downloadable summary in three formats: Word (.docx), HTML and Markdown.

The AI writes the wording (see advice_ai.Summary). The risk-matrix table in the download is
built here from the matrix data, so its numbers are never AI-written text.

No Streamlit imports here, so this module can be unit-tested on its own.
"""

import datetime
import html
import io

from advice_ai import DISCLAIMER, ContractNotes, Recommendation, Summary
from risk_matrix import RiskMatrix, build_tables

# Colours for risk scores 1 (low risk) to 5 (high risk). Also used by the on-screen matrix.
RISK_PALETTE = {1: "#c8e6c9", 2: "#e6f2c2", 3: "#fff3b0", 4: "#ffd699", 5: "#f4a6a6"}


# ---------------------------------------------------------------------------
# Format-neutral document description
# ---------------------------------------------------------------------------
# A document is a list of blocks:
#   ("title", text) ("meta", text) ("h2", text) ("p", text) ("ul", [text, ...]) ("note", text)
#   ("table", headers, rows)   where each row is a list of (text, score_or_None)
Block = tuple


def build_blocks(
    summary: Summary,
    matrix: RiskMatrix,
    rec: Recommendation,
    notes: ContractNotes | None,
) -> list[Block]:
    risk, weights, weighted = build_tables(matrix)

    headers = ["Delivery method"] + [f"{c}\n(weight {weights[c]})" for c in risk.columns] + ["Overall risk"]
    rows = []
    for method in weighted.index:
        row = [(method, None)]
        row += [(f"{int(risk.loc[method, c])}", int(risk.loc[method, c])) for c in risk.columns]
        row.append((f"{weighted[method]:.1f}", float(weighted[method])))
        rows.append(row)

    today = datetime.date.today().strftime("%d %B %Y")
    blocks: list[Block] = [
        ("title", summary.title),
        ("meta", f"Prepared {today} with the Project Delivery Method Selector (educational tool)."),
        ("h2", "Your project"),
        ("p", summary.project_overview),
        ("h2", f"Recommendation: {summary.recommended_method}"),
        ("p", rec.headline),
        ("ul", list(summary.reasons)),
        ("p", summary.runner_up_note),
        ("h2", "Risk matrix"),
        ("table", headers, rows),
        (
            "note",
            "Risk to the principal: 1 = low (green), 5 = high (red). Lower is better. "
            "Methods are ordered from lowest to highest overall risk, and the weight shows how "
            "much each objective counts for this project (1-5).",
        ),
        ("h2", "Risks to manage"),
        ("ul", list(summary.risks_to_manage)),
        ("h2", "Contract points to discuss with your lawyer"),
    ]
    if notes is not None and notes.standard_forms:
        blocks.append(("p", "Standard forms: " + "; ".join(notes.standard_forms)))
    blocks += [
        ("ul", list(summary.contract_points)),
        ("h2", "Next steps"),
        ("ul", list(summary.next_steps)),
        ("note", DISCLAIMER),
    ]
    return blocks


def _score_colour(score) -> str | None:
    if score is None:
        return None
    return RISK_PALETTE[min(5, max(1, int(round(score))))]


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------
def to_markdown(blocks: list[Block]) -> str:
    out: list[str] = []
    for block in blocks:
        kind = block[0]
        if kind == "title":
            out.append(f"# {block[1]}")
        elif kind == "meta":
            out.append(f"*{block[1]}*")
        elif kind == "h2":
            out.append(f"## {block[1]}")
        elif kind == "p":
            out.append(block[1])
        elif kind == "ul":
            out.append("\n".join(f"- {item}" for item in block[1]))
        elif kind == "note":
            out.append(f"*{block[1]}*")
        elif kind == "table":
            _, headers, rows = block
            clean = lambda s: s.replace("\n", " ").replace("|", "\\|")  # noqa: E731
            lines = ["| " + " | ".join(clean(h) for h in headers) + " |"]
            lines.append("|" + "|".join(["---"] * len(headers)) + "|")
            for row in rows:
                lines.append("| " + " | ".join(clean(text) for text, _ in row) + " |")
            out.append("\n".join(lines))
    return "\n\n".join(out) + "\n"


_HTML_CSS = """
body { font-family: Georgia, 'Times New Roman', serif; max-width: 860px; margin: 2rem auto;
       padding: 0 1rem; color: #1a1a1a; line-height: 1.5; }
h1 { font-size: 1.8rem; margin-bottom: .2rem; }
h2 { font-size: 1.2rem; margin-top: 1.8rem; border-bottom: 1px solid #ccc; padding-bottom: .2rem; }
.meta, .note { color: #555; font-size: .9rem; font-style: italic; }
table { border-collapse: collapse; width: 100%; font-size: .85rem; margin: .8rem 0; }
th, td { border: 1px solid #999; padding: 6px 8px; text-align: center; }
th:first-child, td:first-child { text-align: left; }
th { background: #eee; }
@media print { body { margin: 0; max-width: none; } }
"""


def to_html(blocks: list[Block]) -> str:
    esc = html.escape
    title = next((b[1] for b in blocks if b[0] == "title"), "Summary")
    body: list[str] = []
    for block in blocks:
        kind = block[0]
        if kind == "title":
            body.append(f"<h1>{esc(block[1])}</h1>")
        elif kind == "meta":
            body.append(f'<p class="meta">{esc(block[1])}</p>')
        elif kind == "h2":
            body.append(f"<h2>{esc(block[1])}</h2>")
        elif kind == "p":
            body.append(f"<p>{esc(block[1])}</p>")
        elif kind == "ul":
            body.append("<ul>" + "".join(f"<li>{esc(i)}</li>" for i in block[1]) + "</ul>")
        elif kind == "note":
            body.append(f'<p class="note">{esc(block[1])}</p>')
        elif kind == "table":
            _, headers, rows = block
            head = "".join(f"<th>{esc(h).replace(chr(10), '<br>')}</th>" for h in headers)
            trs = []
            for row in rows:
                tds = []
                for text, score in row:
                    colour = _score_colour(score)
                    style = f' style="background:{colour}"' if colour else ""
                    tds.append(f"<td{style}>{esc(text)}</td>")
                trs.append("<tr>" + "".join(tds) + "</tr>")
            body.append(f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(trs)}</tbody></table>")
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{esc(title)}</title><style>{_HTML_CSS}</style></head><body>"
        + "\n".join(body)
        + "</body></html>"
    )


def to_docx(blocks: list[Block]) -> bytes:
    from docx import Document
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt

    doc = Document()
    for section in doc.sections:
        section.left_margin = section.right_margin = Cm(1.5)
        section.top_margin = section.bottom_margin = Cm(2)

    def shade(cell, hex_colour: str) -> None:
        shading = OxmlElement("w:shd")
        shading.set(qn("w:val"), "clear")
        shading.set(qn("w:color"), "auto")
        shading.set(qn("w:fill"), hex_colour.lstrip("#"))
        cell._tc.get_or_add_tcPr().append(shading)

    def fill_cell(cell, text: str, bold: bool = False, centre: bool = False, size: int = 9) -> None:
        paragraph = cell.paragraphs[0]
        run = paragraph.add_run(text)
        run.font.size = Pt(size)
        run.bold = bold
        if centre:
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER

    for block in blocks:
        kind = block[0]
        if kind == "title":
            doc.add_heading(block[1], level=0)
        elif kind == "meta":
            doc.add_paragraph().add_run(block[1]).italic = True
        elif kind == "h2":
            doc.add_heading(block[1], level=1)
        elif kind == "p":
            doc.add_paragraph(block[1])
        elif kind == "ul":
            for item in block[1]:
                doc.add_paragraph(item, style="List Bullet")
        elif kind == "note":
            run = doc.add_paragraph().add_run(block[1])
            run.italic = True
            run.font.size = Pt(9)
        elif kind == "table":
            _, headers, rows = block
            table = doc.add_table(rows=1, cols=len(headers))
            table.style = "Table Grid"
            table.autofit = False
            for i, header in enumerate(headers):
                fill_cell(table.rows[0].cells[i], header, bold=True, centre=i > 0, size=8)
            for row in rows:
                cells = table.add_row().cells
                for i, (text, score) in enumerate(row):
                    fill_cell(cells[i], text, centre=i > 0)
                    colour = _score_colour(score)
                    if colour:
                        shade(cells[i], colour)
            # First column wider (method names), the rest equal. Total = 18 cm of text width.
            other = Cm(14.4 / (len(headers) - 1))
            for row in table.rows:
                for i, cell in enumerate(row.cells):
                    cell.width = Cm(3.6) if i == 0 else other

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()