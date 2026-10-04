import re
from typing import Dict, List, Tuple

from graph.schemas import ParsedJD, MatchResult, KeywordAnalysis, KeywordGroup, Verdict, ReqType
from utils.textnorm import normalize, term_in_text

KW_TYPES = {ReqType.SKILL, ReqType.TOOL, ReqType.CERTIFICATION}   # only these produce keywords
SUPPORT_TYPES = {ReqType.SKILL, ReqType.TOOL}                      # only these can "support" one
CASE_SENSITIVE = {"it", "go", "as", "or", "us", "an", "he", "me"}  # ordinary words: match capitalisation
GENERIC = {"skills", "skill", "experience", "degree", "bachelor", "bachelors", "bachelor s", "master",
           "masters", "related field", "related", "field", "equivalent", "equivalent experience",
           "eligibility", "education", "knowledge", "ability", "requirements", "years", "strong",
           "excellent", "communication", "teamwork", "team", "work", "role", "candidate", "plus",
           "scratch", "organize", "archive", "manage", "maintain", "ensure", "collaborate",
           "original", "creative", "detail", "records", "business opportunities"}
_YEARS = re.compile(r"\d+\s*\+?\s*(?:years?|yrs?)", re.I)


def _usable(k: str) -> bool:
    n = normalize(k)
    return bool(n) and len(k) <= 40 and n not in GENERIC and not _YEARS.search(k)


def _in_cv(k: str, norm_cv: str, raw_cv: str) -> bool:
    if normalize(k) in CASE_SENSITIVE:
        return re.search(rf"(?<!\w){re.escape(k)}(?!\w)", raw_cv) is not None
    return term_in_text(k, norm_cv)


def analyze_keywords(jd: ParsedJD, results: List[MatchResult],
                     cv_text: str) -> Tuple[KeywordAnalysis, Dict[str, str]]:
    """Returns (KeywordAnalysis with groups, {supported keyword: CV evidence}). Pure code, no LLM."""
    norm_cv = normalize(cv_text)
    res_by_id = {r.requirement_id: r for r in results}
    used, groups, evidence = set(), [], {}

    def support_for(term: str):
        nk = normalize(term)
        for req in jd.requirements:
            if req.min_years or req.type not in SUPPORT_TYPES:
                continue
            linked = any(normalize(x) == nk for x in req.keywords) or term_in_text(term, normalize(req.text))
            res = res_by_id.get(req.id)
            if linked and res and res.verdict == Verdict.MEETS and res.verified and res.evidence_snippet:
                return res.evidence_snippet
        return ""

    for req in jd.requirements:
        if req.type not in KW_TYPES:
            continue
        nreq = normalize(req.text)
        cands = list(req.keywords) + [k for k in jd.keywords if term_in_text(k, nreq)]
        terms = []
        for k in cands:
            k = (k or "").strip()
            key = normalize(k)
            if k and key not in used and _usable(k):
                used.add(key)
                terms.append(k)
        if not terms:
            continue
        g = KeywordGroup(requirement=req.text)
        for k in terms:
            if _in_cv(k, norm_cv, cv_text):
                g.present.append(k)
                continue
            ev = support_for(k)
            if ev:
                g.supported.append(k)
                evidence[k] = ev
            else:
                g.unsupported.append(k)
        groups.append(g)

    return KeywordAnalysis(
        present=[k for g in groups for k in g.present],
        missing_supported=[k for g in groups for k in g.supported],
        missing_unsupported=[k for g in groups for k in g.unsupported],
        groups=groups), evidence
