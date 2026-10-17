"""Turn fetched HTML / PDF bytes into clean text."""
import html as htmllib
import re

import pymupdf
import trafilatura
from bs4 import BeautifulSoup


# soft hyphens left by PDF line breaks: "house\xad holds" -> "households"
SOFT_HYPHEN = re.compile(r"\xad\s*")


def clean_ws(text: str) -> str:
    text = htmllib.unescape(text or "")
    text = text.replace("\xa0", " ")
    text = SOFT_HYPHEN.sub("", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def html_fragment_to_text(fragment: str) -> str:
    """WordPress `content.rendered` -> text, keeping paragraph breaks."""
    soup = BeautifulSoup(fragment or "", "lxml")
    for t in soup(["script", "style", "figure", "noscript"]):
        t.decompose()
    blocks = [b.get_text(" ", strip=True) for b in soup.find_all(["p", "li", "h2", "h3", "h4", "blockquote", "td"])]
    text = "\n\n".join(b for b in blocks if b)
    if len(text) < 0.5 * len(soup.get_text(" ", strip=True)):
        text = soup.get_text("\n", strip=True)
    return clean_ws(text)


def html_page_to_text(html: str, url: str | None = None) -> str:
    text = trafilatura.extract(html, url=url, include_comments=False, include_tables=True, favor_precision=True)
    if not text:
        soup = BeautifulSoup(html, "lxml")
        main = soup.find("article") or soup.find("main") or soup.body or soup
        text = main.get_text("\n", strip=True)
    return clean_ws(text)


def links_in_fragment(fragment: str) -> list[str]:
    soup = BeautifulSoup(fragment or "", "lxml")
    return [a["href"] for a in soup.find_all("a", href=True)]


_HYPHEN_BREAK = re.compile(r"(\w)-\n(\w)")
_LINE_BREAK = re.compile(r"\s*\n\s*")


def pdf_pages(data: bytes) -> tuple[list[str], dict]:
    """Return (page_texts, pdf_metadata). Empty texts => probably a scanned PDF."""
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        pages = []
        for p in doc:
            # text blocks follow the column layout; join hard line breaks inside a block so
            # sentences are not cut in pieces (MyGov is a multi-column newspaper)
            blocks = [b[4] for b in p.get_text("blocks", sort=False) if b[6] == 0]
            joined = [_LINE_BREAK.sub(" ", _HYPHEN_BREAK.sub(r"\1\2", b)).strip() for b in blocks]
            pages.append(clean_ws("\n\n".join(j for j in joined if j)))
        meta = dict(doc.metadata or {})
    return pages, meta


def docx_text(data: bytes) -> str:
    """Minimal DOCX reader (zip + XML) so we do not need python-docx."""
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(data)) as z:
        xml = z.read("word/document.xml").decode("utf-8", "ignore")
    xml = re.sub(r"</w:p>", "\n\n", xml)
    return clean_ws(re.sub(r"<[^>]+>", "", xml))
