import re
import unicodedata


def normalize(s: str) -> str:
    """Lowercase, drop punctuation noise, collapse whitespace. Keeps + # . / so c++, c#, node.js, ci/cd survive."""
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = re.sub(r"[-\u2013\u2014\u2022\u25cf\u25aa]", " ", s)
    s = re.sub(r"[^\w\s+#./]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def term_in_text(term: str, norm_text: str) -> bool:
    """Whole-term match on already-normalized text ('r' will not match inside 'react')."""
    t = normalize(term)
    if not t:
        return False
    return re.search(rf"(?<!\w){re.escape(t)}(?!\w)", norm_text) is not None
