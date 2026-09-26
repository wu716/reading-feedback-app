import zipfile
from pathlib import Path

from app.routers.ebooks import _parse_epub


def _make_epub(path: Path):
    opf = '''<package xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><metadata><dc:title xmlns:dc="http://purl.org/dc/elements/1.1/">The Half Second</dc:title></metadata><manifest><item id="c1" href="c1.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="c1"/></spine></package>'''
    container = '''<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="content.opf"/></rootfiles></container>'''
    chapter = '<html><head><title>Converted Ebook</title></head><body><h1>First reactions</h1><p>Memory is not an undivided thing.</p></body></html>'
    with zipfile.ZipFile(path, "w") as book:
        book.writestr("mimetype", "application/epub+zip")
        book.writestr("META-INF/container.xml", container)
        book.writestr("content.opf", opf)
        book.writestr("c1.xhtml", chapter)


def test_generic_html_title_uses_heading(tmp_path):
    path = tmp_path / "book.epub"
    _make_epub(path)
    title, chapters = _parse_epub(path)
    assert title == "The Half Second"
    assert chapters[0]["title"] == "First reactions"
