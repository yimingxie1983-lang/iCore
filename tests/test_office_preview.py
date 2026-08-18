from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
from xml.etree.ElementTree import Element, SubElement, tostring

from cancer_claw.services.office_preview import office_format, office_snippet, preview_office


W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _docx(path: Path, paragraphs: list[str]) -> None:
    document = Element(f"{{{W}}}document")
    body = SubElement(document, f"{{{W}}}body")
    for text in paragraphs:
        p = SubElement(body, f"{{{W}}}p")
        r = SubElement(p, f"{{{W}}}r")
        t = SubElement(r, f"{{{W}}}t")
        t.text = text
    xml = tostring(document, encoding="utf-8", xml_declaration=True)
    with ZipFile(path, "w", ZIP_DEFLATED) as zf:
        zf.writestr("word/document.xml", xml)


def _xlsx(path: Path) -> None:
    wb = (
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="数据" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )
    rels = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )
    sheet = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheetData>"
        '<row r="1">'
        '<c r="A1" t="inlineStr"><is><t>姓名</t></is></c>'
        '<c r="B1" t="inlineStr"><is><t>年龄</t></is></c>'
        "</row>"
        '<row r="2">'
        '<c r="A2" t="inlineStr"><is><t>Ada</t></is></c>'
        '<c r="B2"><v>36</v></c>'
        "</row>"
        "</sheetData></worksheet>"
    )
    with ZipFile(path, "w", ZIP_DEFLATED) as zf:
        zf.writestr("xl/workbook.xml", wb.encode("utf-8"))
        zf.writestr("xl/_rels/workbook.xml.rels", rels.encode("utf-8"))
        zf.writestr("xl/worksheets/sheet1.xml", sheet.encode("utf-8"))


def test_office_format_detects_ooxml():
    assert office_format(Path("a.docx")) == "docx"
    assert office_format(Path("a.xlsx")) == "xlsx"
    assert office_format(Path("a.pptx")) == "pptx"
    assert office_format(Path("a.doc")) == "legacy"
    assert office_format(Path("a.md")) is None


def test_preview_docx_extracts_paragraphs(tmp_path: Path):
    path = tmp_path / "trial.docx"
    _docx(path, ["临床试验方案", "入排标准见下。"])
    payload = preview_office(path)
    assert payload["kind"] == "docx"
    assert "临床试验方案" in payload["paragraphs"]
    snippet, truncated = office_snippet(path)
    assert "临床试验方案" in snippet
    assert truncated is False


def test_preview_xlsx_extracts_sheet(tmp_path: Path):
    path = tmp_path / "table.xlsx"
    _xlsx(path)
    payload = preview_office(path, max_rows=20)
    assert payload["kind"] == "xlsx"
    sheet = payload["sheets"][0]
    assert sheet["name"] == "数据"
    assert "姓名" in sheet["columns"]
    assert any("Ada" in row for row in sheet["rows"])
