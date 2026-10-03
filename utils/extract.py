import io
import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Optional

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_PAGES = 6
LIMITS = {"cv": 12000, "jd": 8000}      # max characters sent onward
MIN_CHARS = {"cv": 200, "jd": 50}       # below this we treat it as "nothing readable"
LABEL = {"cv": "CV", "jd": "job description"}


class ExtractionError(Exception):
    """Message is always safe to show directly to the user."""


@dataclass
class ExtractResult:
    text: str
    source: str                          # "pdf" | "docx" | "txt" | "paste"
    pages: int = 0
    truncated: bool = False
    warnings: List[str] = field(default_factory=list)


# ---------- Cleaning ----------
_BULLET_START = re.compile(r"(?m)^[ \t]*[•●○▪■◦►➢▶❖\uf000-\uf8ff][ \t]*")
_PRIVATE_USE = re.compile(r"[\uf000-\uf8ff]")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_HYPHEN_BREAK = re.compile(r"(?<=[a-z])-\n(?=[a-z])")


def clean_text(raw: str) -> str:
    t = unicodedata.normalize("NFKC", raw)      # also fixes ligatures like ﬁ -> fi
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    t = _CONTROL.sub("", t)
    t = _BULLET_START.sub("- ", t)
    t = _PRIVATE_USE.sub("", t)
    t = _HYPHEN_BREAK.sub("", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = "\n".join(line.strip() for line in t.split("\n"))
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


# ---------- PDF ----------
def _looks_two_column(page) -> bool:
    """True if there is a clear empty gutter down the middle of the page."""
    words = page.extract_words()
    if len(words) < 80:
        return False
    mid, band = page.width / 2, page.width * 0.04
    crossing = sum(1 for w in words if w["x0"] < mid + band and w["x1"] > mid - band)
    left = sum(1 for w in words if w["x1"] <= mid - band)
    right = sum(1 for w in words if w["x0"] >= mid + band)
    n = len(words)
    return crossing < 0.03 * n and left > 0.25 * n and right > 0.25 * n


def _read_pdf(data: bytes, warnings: List[str]):
    import pdfplumber
    try:
        pdf = pdfplumber.open(io.BytesIO(data))
    except Exception as e:
        if "password" in type(e).__name__.lower():
            raise ExtractionError("This PDF is password-protected. Remove the password or paste the text instead.")
        raise ExtractionError("Couldn't open this PDF. It may be corrupted. Please paste the text instead.")

    texts, two_col = [], False
    with pdf:
        total = len(pdf.pages)
        if total > MAX_PAGES:
            warnings.append(f"Only the first {MAX_PAGES} of {total} pages were read.")
        for page in pdf.pages[:MAX_PAGES]:
            try:
                if _looks_two_column(page):
                    two_col = True
                    mid = page.width / 2
                    left = page.crop((0, 0, mid, page.height)).extract_text(x_tolerance=2, y_tolerance=3) or ""
                    right = page.crop((mid, 0, page.width, page.height)).extract_text(x_tolerance=2, y_tolerance=3) or ""
                    texts.append(left + "\n" + right)
                else:
                    texts.append(page.extract_text(x_tolerance=2, y_tolerance=3) or "")
            except Exception:
                texts.append("")                      # one bad page shouldn't kill the file
    if two_col:
        warnings.append("Two-column layout detected. Please check the preview to make sure the order is right.")
    return "\n\n".join(texts), total


# ---------- DOCX ----------
def _read_docx(data: bytes) -> str:
    try:
        from docx import Document
        from docx.table import Table
        from docx.text.paragraph import Paragraph
        doc = Document(io.BytesIO(data))
    except Exception:
        raise ExtractionError("Couldn't open this Word file. Try saving it as PDF or paste the text instead.")

    lines = []
    for child in doc.element.body.iterchildren():      # keeps paragraphs and tables in order
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            lines.append(Paragraph(child, doc).text)
        elif tag == "tbl":
            for row in Table(child, doc).rows:
                seen, cells = [], []
                for c in row.cells:
                    if any(c._tc is s for s in seen):  # merged cells repeat
                        continue
                    seen.append(c._tc)
                    txt = c.text.strip()
                    if txt:
                        cells.append(txt)
                if cells:
                    lines.append(" | ".join(cells))
    return "\n".join(lines)


# ---------- TXT ----------
def _read_txt(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


# ---------- Shared finishing step ----------
def _finalize(raw: str, kind: str, source: str, pages: int, warnings: List[str]) -> ExtractResult:
    text = clean_text(raw)
    label = LABEL[kind]

    if len(text) < MIN_CHARS[kind]:
        if source == "pdf":
            raise ExtractionError(
                f"Couldn't read any text from this PDF. It is probably scanned or image-based. "
                f"Please paste your {label} text instead.")
        if source == "docx":
            raise ExtractionError(
                f"Almost no text found in this Word file. If the content is in text boxes or images, "
                f"please paste your {label} text instead.")
        raise ExtractionError(f"The {label} text is too short to analyse. Please provide more detail.")

    truncated = False
    limit = LIMITS[kind]
    if len(text) > limit:
        cut = text[:limit]
        nl = cut.rfind("\n")
        if nl > limit * 0.8:                          # cut at a line break if one is near the end
            cut = cut[:nl]
        text = cut.rstrip()
        truncated = True
        warnings.append(f"The {label} was long, so only the first {len(text):,} characters are used.")

    return ExtractResult(text=text, source=source, pages=pages, truncated=truncated, warnings=warnings)


# ---------- Public API ----------
def extract_text(data: bytes, filename: str, kind: str = "cv") -> ExtractResult:
    """kind: 'cv' or 'jd'. Raises ExtractionError with a user-friendly message."""
    if kind not in LIMITS:
        raise ValueError("kind must be 'cv' or 'jd'")
    if not data:
        raise ExtractionError("The uploaded file is empty.")
    if len(data) > MAX_FILE_BYTES:
        raise ExtractionError(f"File is too large (max {MAX_FILE_BYTES // (1024 * 1024)} MB).")

    name = (filename or "").lower().strip()
    warnings: List[str] = []

    if name.endswith(".pdf"):
        raw, pages = _read_pdf(data, warnings)
        return _finalize(raw, kind, "pdf", pages, warnings)
    if name.endswith(".docx"):
        return _finalize(_read_docx(data), kind, "docx", 0, warnings)
    if name.endswith(".txt"):
        return _finalize(_read_txt(data), kind, "txt", 0, warnings)
    if name.endswith(".doc"):
        raise ExtractionError("Old .doc files aren't supported. Please save as .docx or PDF, or paste the text.")
    raise ExtractionError("Unsupported file type. Please upload a PDF, DOCX or TXT file, or paste the text.")


def prepare_pasted(text: str, kind: str = "cv") -> ExtractResult:
    if kind not in LIMITS:
        raise ValueError("kind must be 'cv' or 'jd'")
    return _finalize(text or "", kind, "paste", 0, [])


def resolve_input(kind: str, pasted: str = "", upload_bytes: Optional[bytes] = None,
                  upload_name: str = "") -> ExtractResult:
    """Upload wins if present, otherwise use pasted text."""
    if upload_bytes:
        return extract_text(upload_bytes, upload_name, kind)
    if pasted and pasted.strip():
        return prepare_pasted(pasted, kind)
    raise ExtractionError(f"Please upload your {LABEL[kind]} or paste its text.")
