from datetime import date
from typing import Dict, List, Optional

from rapidfuzz import fuzz

from graph import advice
from graph.matcher import LLMMatch
from graph.schemas import ParsedCV, JDRequirement, MatchResult, Verdict, ReqType, LEVELS, norm_level
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


# ---------- Education field check ----------
_EDU_GENERIC = {"bachelor", "bachelors", "bachelor s", "master", "masters", "master s", "phd", "doctorate",
                "degree", "diploma", "related", "relevant", "similar", "field", "fields", "discipline",
                "or", "and", "in", "of", "a", "an", "the", "any", "science", "sciences", "equivalent",
                "experience", "engineering", "bs", "bsc", "ba", "ms", "msc", "mba", "required", "preferred",
                "from", "accredited", "university", "technical", "subject", "such", "as", "to", "with", "s"}
_EDU_GROUPS = [{"cs", "computer"}, {"it", "information", "technology"}, {"ee", "electrical"},
               {"se", "software"}, {"ds", "data"}]


def education_field_ok(req_text: str, snippet: str) -> bool:
    """True if the degree quoted from the CV mentions a field named in the requirement.
    If the requirement names no specific field, there is nothing to check."""
    terms = {t for t in normalize(req_text).split() if t not in _EDU_GENERIC and len(t) > 1}
    if not terms:
        return True
    have = set(normalize(snippet).split())
    for t in terms:
        alts = {t}
        for g in _EDU_GROUPS:
            if t in g:
                alts |= g
        if alts & have:
            return True
    return False


# ---------- Years of experience ----------
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


# ---------- Verdict checks ----------
def _verify_one(req: JDRequirement, m: LLMMatch, norm_cv: str) -> MatchResult:
    snippet = (m.evidence_snippet or "").strip()
    reason = (m.reason or "").strip()[:300]
    ok = bool(snippet) and snippet_in_cv(snippet, norm_cv)
    verdict = m.verdict
    if verdict == Verdict.MEETS and not ok:
        verdict = Verdict.UNCLEAR
        reason = ("Downgraded from 'meets': no matching evidence was found in the CV text. " + reason).strip()
    if verdict == Verdict.DOES_NOT_MEET and req.type in (ReqType.TOOL, ReqType.SKILL) and not ok:
        verdict = Verdict.UNCLEAR                          # absent tool/skill = no evidence, not a proven miss
        reason = advice.NO_MENTION
    if verdict == Verdict.MEETS and ok and req.type == ReqType.EDUCATION and not education_field_ok(req.text, snippet):
        verdict = Verdict.UNCLEAR
        reason = ("The degree in the CV doesn't clearly match the field this requirement asks for. "
                  "Check this one manually.")
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
        m = by_id.get(req.id)
        if req.type == ReqType.SOFT_SKILL:
            res = MatchResult(requirement_id=req.id, verdict=Verdict.CANNOT_ASSESS,
                              reason="Soft skills can't be reliably judged from a CV.")
            out.append(advice.finish(req, res, m))
            continue

        res, years_row = None, False
        if req.min_years:
            res = _experience_override(req, m, cv, today)
            years_row = res is not None
        if res is None:
            if m is None:
                res = MatchResult(requirement_id=req.id, verdict=Verdict.UNCLEAR,
                                  reason="The model did not return a result for this requirement.")
            else:
                res = _verify_one(req, m, norm_cv)
                have, need = norm_level(m.cv_level), norm_level(req.required_level)
                res.cv_level = have
                if req.min_years and res.verdict == Verdict.MEETS:   # years can't be confirmed -> don't claim it
                    res.verdict = Verdict.UNCLEAR
                    res.reason = ("Required years of experience couldn't be confirmed from dated roles. "
                                  + res.reason).strip()
                elif res.verified and have and need and LEVELS.index(have) < LEVELS.index(need):
                    res.level_gap = True                              # the CV states a lower level than the job asks
                    if res.verdict == Verdict.MEETS:
                        res.verdict = Verdict.DOES_NOT_MEET
                        res.reason = f"Your CV describes {have} level; the job asks for {need} level."
        out.append(advice.finish(req, res, m, years_row))
    return out
