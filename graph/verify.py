from datetime import date
from typing import Dict, List, Optional

from rapidfuzz import fuzz

from graph.matcher import LLMMatch
from graph.schemas import ParsedCV, JDRequirement, MatchResult, Verdict, ReqType
from utils.experience import years_of_experience, fmt_years
from utils.textnorm import normalize, term_in_text

FUZZY_THRESHOLD = 90
MAX_SNIPPET = 400        # longer than this = the model dumped a section, not a quote
SHORT_SNIPPET = 20       # below this, fuzzy matching is meaningless: require a whole-term match


def snippet_in_cv(snippet: str, norm_cv: str) -> bool:
    """True if the quoted snippet really appears in the CV (norm_cv = normalize(cv_text))."""
    s = normalize(snippet)
    if len(s) < 2 or len(snippet) > MAX_SNIPPET:
        return False
    if len(s) < SHORT_SNIPPET:
        return term_in_text(snippet, norm_cv)
    if s in norm_cv:
        return True
    return fuzz.partial_ratio(s, norm_cv) >= FUZZY_THRESHOLD


def _experience_override(req: JDRequirement, m: Optional[LLMMatch], cv: ParsedCV,
                         today: date) -> Optional[MatchResult]:
    """Code decides years-based verdicts from the dated jobs the LLM marked as relevant."""
    nums = sorted({n for n in (m.relevant_job_numbers if m else []) if 1 <= n <= len(cv.jobs)})
    if not nums:
        return None
    jobs = [cv.jobs[n - 1] for n in nums]
    exp = years_of_experience(jobs, today)
    if exp.jobs_used == 0:
        return None
    need = req.min_years
    got = fmt_years(exp.low, exp.high)
    evidence = "; ".join(
        f"{j.title or 'Role'}, {j.company or 'company'} ({j.start or '?'} to {j.end or '?'})" for j in jobs)

    if exp.low + 1e-9 >= need:
        verdict = Verdict.MEETS
        reason = f"About {got} years across the relevant roles (required: {need:g}+)."
    elif exp.high + 1e-9 < need and exp.undated == 0:
        verdict = Verdict.DOES_NOT_MEET
        reason = f"CV shows about {got} years of relevant experience; {need:g}+ required."
    else:
        verdict = Verdict.UNCLEAR
        reason = (f"About {got} years found; {need:g}+ required. Some dates are missing or only "
                  f"given as years, so this can't be confirmed.")
    return MatchResult(requirement_id=req.id, verdict=verdict, evidence_snippet=evidence,
                       reason=reason, verified=(verdict == Verdict.MEETS))


def _verify_one(req: JDRequirement, m: LLMMatch, norm_cv: str) -> MatchResult:
    snippet = (m.evidence_snippet or "").strip()
    reason = (m.reason or "").strip()[:300]
    ok = bool(snippet) and snippet_in_cv(snippet, norm_cv)
    verdict = m.verdict
    if verdict == Verdict.MEETS and not ok:
        verdict = Verdict.UNCLEAR
        reason = ("Downgraded from 'meets': no matching evidence was found in the CV text. " + reason).strip()
    if not ok:
        snippet = ""                                       # never show unverified "evidence"
    return MatchResult(requirement_id=req.id, verdict=verdict, evidence_snippet=snippet,
                       reason=reason, verified=ok)


def finalize_results(requirements: List[JDRequirement], matches: List[LLMMatch], cv: ParsedCV,
                     cv_text: str, today: Optional[date] = None) -> List[MatchResult]:
    """One MatchResult per requirement, in JD order, always."""
    today = today or date.today()
    norm_cv = normalize(cv_text)
    by_id: Dict[str, LLMMatch] = {}
    for m in matches:
        by_id.setdefault(m.requirement_id.strip(), m)      # first answer wins; unknown ids are ignored

    out: List[MatchResult] = []
    for req in requirements:
        if req.type == ReqType.SOFT_SKILL:
            out.append(MatchResult(requirement_id=req.id, verdict=Verdict.CANNOT_ASSESS,
                                   reason="Soft skills can't be reliably judged from a CV."))
            continue
        m = by_id.get(req.id)
        if req.min_years:
            res = _experience_override(req, m, cv, today)
            if res:
                out.append(res)
                continue
        if m is None:
            out.append(MatchResult(requirement_id=req.id, verdict=Verdict.UNCLEAR,
                                   reason="The model did not return a result for this requirement."))
            continue
        res = _verify_one(req, m, norm_cv)
        if req.min_years and res.verdict == Verdict.MEETS:  # years can't be confirmed -> don't claim it
            res.verdict = Verdict.UNCLEAR
            res.reason = ("Required years of experience couldn't be confirmed from dated roles. "
                          + res.reason).strip()
        out.append(res)
    return out
