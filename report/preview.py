"""Render a .docx to PDF with Word, then to page images, so the layout can be seen.

Run:  python report/preview.py <file.docx> [first_page] [last_page]
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).parent
PREVIEW = HERE / "preview"


def to_pdf(docx: Path) -> Path:
    import shutil
    import tempfile

    import pythoncom
    import win32com.client

    pdf = PREVIEW / (docx.stem + ".pdf")
    PREVIEW.mkdir(exist_ok=True)

    # Open a copy: Word blocks indefinitely if the original is already open
    # in another Word window, even in read-only mode.
    scratch = Path(tempfile.mkdtemp(prefix="pqc_preview_")) / docx.name
    shutil.copy2(docx, scratch)

    pythoncom.CoInitialize()
    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        doc = word.Documents.Open(str(scratch), ReadOnly=True,
                                  AddToRecentFiles=False, Visible=False)
        try:
            # Repaginate so field-driven page counts settle before export.
            doc.Repaginate()
            pages = doc.ComputeStatistics(2)  # wdStatisticPages
            print(f"word reports {pages} pages")
            doc.ExportAsFixedFormat(OutputFileName=str(pdf.resolve()),
                                    ExportFormat=17, OpenAfterExport=False)
        finally:
            doc.Close(SaveChanges=0)
    finally:
        word.Quit()
        pythoncom.CoUninitialize()
    return pdf


def to_images(pdf: Path, first=1, last=None, dpi=110) -> list[Path]:
    import pymupdf

    out: list[Path] = []
    with pymupdf.open(str(pdf)) as document:
        total = document.page_count
        last = min(last or total, total)
        print(f"pdf has {total} pages; rendering {first}-{last}")
        for number in range(first - 1, last):
            page = document.load_page(number)
            pixmap = page.get_pixmap(dpi=dpi)
            path = PREVIEW / f"{pdf.stem}_p{number + 1:03d}.png"
            pixmap.save(str(path))
            out.append(path)
    return out


if __name__ == "__main__":
    source = Path(sys.argv[1])
    first = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    last = int(sys.argv[3]) if len(sys.argv) > 3 else None
    pdf = to_pdf(source)
    for image in to_images(pdf, first, last):
        print(image)
