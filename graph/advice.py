from graph.schemas import ReqType, Verdict, Strength, Fix, norm_claim

NO_MENTION = "No mention found in the CV, so it can't be confirmed either way."

_WHERE = {ReqType.CERTIFICATION: "Certifications section",
          ReqType.EDUCATION: "Education section",
          ReqType.EXPERIENCE: "the dates and bullets of the relevant job",
          ReqType.OTHER: "Summary or a relevant bullet"}
_WHERE_TRAIN = {ReqType.CERTIFICATION: "Certifications section, once earned"}


def where_to(req_type, fix) -> str:
    """Which CV section to edit. Empty for skills/tools (the group note covers those) and hard gaps."""
    try:
        t = ReqType(req_type)
    except ValueError:
        t = ReqType.OTHER
    if fix in (Fix.NONE, Fix.GENUINE_GAP) or t in (ReqType.SKILL, ReqType.TOOL, ReqType.SOFT_SKILL):
        return ""
    return _WHERE_TRAIN.get(t, "") if fix == Fix.TRAINABLE else _WHERE.get(t, "")


def _strength(req, res, m, years_row) -> Strength:
    if req.type == ReqType.SOFT_SKILL or res.verdict == Verdict.CANNOT_ASSESS:
        return Strength.UNAVAILABLE
    if years_row:                                   # computed from dated jobs
        return Strength.STRONG if res.verdict == Verdict.MEETS else Strength.PARTIAL
    if not (res.verified and res.evidence_snippet):
        return Strength.NONE
    if req.type == ReqType.EDUCATION and res.verdict != Verdict.MEETS:
        return Strength.NONE                        # the quoted degree is a different one
    claimed = norm_claim(m.strength) if m else ""
    if res.verdict == Verdict.MEETS:
        if claimed in ("strong", "partial", "weak"):
            return Strength(claimed)
        return Strength.STRONG if len(res.evidence_snippet) >= 40 else Strength.WEAK
    if res.level_gap or claimed in ("strong", "partial"):
        return Strength.PARTIAL
    return Strength.WEAK


def _fix(req, res) -> Fix:
    v, t = res.verdict, req.type
    if v == Verdict.CANNOT_ASSESS or t == ReqType.SOFT_SKILL:
        return Fix.NONE
    if v == Verdict.MEETS:
        return Fix.CV_FIXABLE if res.strength == Strength.WEAK else Fix.NONE
    if t == ReqType.EDUCATION:                      # a different degree is quoted: rewording can't change it
        return Fix.GENUINE_GAP if res.evidence_snippet else Fix.CV_FIXABLE
    if t == ReqType.EXPERIENCE or req.min_years:
        return Fix.GENUINE_GAP if v == Verdict.DOES_NOT_MEET else Fix.CV_FIXABLE
    if res.level_gap or v == Verdict.DOES_NOT_MEET:
        return Fix.TRAINABLE
    return Fix.CV_FIXABLE                           # not mentioned or not clear: may only need better wording


def finish(req, res, m=None, years_row=False):
    res.strength = _strength(req, res, m, years_row)
    res.fix = _fix(req, res)
    return res
