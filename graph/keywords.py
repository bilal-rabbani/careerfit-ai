import re
from typing import Dict, List, Tuple

from graph.schemas import ParsedJD, MatchResult, KeywordAnalysis, Verdict, ReqType
from utils.textnorm import normalize, term_in_text

KW_TYPES = {ReqType.SKILL, ReqType.TOOL, ReqType.CERTIFICATION}   # only these produce keywords
SUPPORT_TYPES = {ReqType.SKILL, ReqType.TOOL}                      # only these can "support" one
CASE_SENSITIVE = {"it", "go", "as", "or", "us", "an", "he", "me"}  # ordinary words: match capitalisation
GENERIC = {"skills", "skill", "experience", "degree", "bachelor", "bachelors", "bachelor s", "master",
           "masters", "related field", "related", "field", "equivalent", "equivalent experience",
           "eligibility", "education", "knowledge", "ability", "requirements", "years", "strong",
           "excellent", "communication", "teamwork", "team", "work", "role", "candidate", "plus"}
_YEARS = re.compile(r"\d+\s*\+?\s*(?:years?|yrs?)", re.I)


def _usable(k: str) -> bool:
    n = normalize(k)
    return bool(n) and len(k) <= 40 and n not in GENERIC and not _YEARS.search(k)


def _in_cv(k: str, norm_cv: str, raw_cv: str) -> bool:
    if normalize(k) in CASE_SENSITIVE:
        return re.search(rf"(?<!\\w){re.escape(k)}(?!\\w)", raw_cv) is not None
    return term_in_text(k, norm_cv)


def analyze_keywords(jd: ParsedJD, results: List[MatchResult],
                     cv_text: str) -> Tuple[KeywordAnalysis, Dict[str, str]]:
    """Returns (KeywordAnalysis, {supported keyword: CV evidence snippet}). Pure code, no LLM."""
    norm_cv = normalize(cv_text)
    res_by_id = {r.requirement_id: r for r in results}
    eligible = [r for r in jd.requirements if r.type in KW_TYPES]
    elig_norm = [normalize(r.text) for r in eligible]

    candidates = [k for k in jd.keywords if any(term_in_text(k, t) for t in elig_norm)]
    candidates += [k for r in eligible for k in r.keywords]

    seen, kws = set(), []
    for k in candidates:
        k = (k or "").strip()
        key = normalize(k)
        if k and key not in seen and _usable(k):
            seen.add(key)
            kws.append(k)

    present, supported, unsupported, evidence = [], [], [], {}
    for k in kws:
        if _in_cv(k, norm_cv, cv_text):
            present.append(k)
            continue
        nk, found = normalize(k), None
        for req in jd.requirements:
            if req.min_years or req.type not in SUPPORT_TYPES:
                continue
            linked = any(normalize(x) == nk for x in req.keywords) or term_in_text(k, normalize(req.text))
            res = res_by_id.get(req.id)
            if linked and res and res.verdict == Verdict.MEETS and res.verified and res.evidence_snippet:
                found = res.evidence_snippet
                break
        if found:
            supported.append(k)
            evidence[k] = found
        else:
            unsupported.append(k)

    return KeywordAnalysis(present=present, missing_supported=supported,
                           missing_unsupported=unsupported), evidence
