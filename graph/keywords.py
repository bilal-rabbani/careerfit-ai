from typing import Dict, List, Tuple

from graph.schemas import ParsedJD, MatchResult, KeywordAnalysis, Verdict
from utils.textnorm import normalize, term_in_text


def analyze_keywords(jd: ParsedJD, results: List[MatchResult],
                     cv_text: str) -> Tuple[KeywordAnalysis, Dict[str, str]]:
    """Returns (KeywordAnalysis, {supported keyword: CV evidence snippet}). Pure code, no LLM."""
    norm_cv = normalize(cv_text)
    res_by_id = {r.requirement_id: r for r in results}

    seen, kws = set(), []
    for k in list(jd.keywords) + [k for r in jd.requirements for k in r.keywords]:
        k = (k or "").strip()
        key = normalize(k)
        if k and key not in seen:
            seen.add(key)
            kws.append(k)

    present, supported, unsupported, evidence = [], [], [], {}
    for k in kws:
        if term_in_text(k, norm_cv):
            present.append(k)                              # already written in the CV
            continue
        nk, found = normalize(k), None
        for req in jd.requirements:
            if req.min_years:                              # "years" evidence doesn't prove a tool
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
