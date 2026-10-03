import re
from collections import Counter
from typing import Dict, List

from rapidfuzz import fuzz

from graph.schemas import ParsedJD, MatchResult, KeywordAnalysis, BulletSuggestion
from utils.textnorm import normalize, term_in_text

FIND_THRESHOLD = 75
_NUM = re.compile(r"\d+(?:[.,]\d+)?")


def _list(x):
    return [x] if isinstance(x, str) else list(x)


def _years_ok(gold, got) -> bool:
    if gold is None or got is None:
        return gold is None and got is None
    return abs(float(gold) - float(got)) < 0.01


def map_gold(gold: List[dict], reqs) -> Dict[int, tuple]:
    """One-to-one fuzzy match: gold index -> (parsed index, score)."""
    pairs = sorted(((fuzz.token_set_ratio(normalize(g["text"]), normalize(r.text)), gi, ri)
                    for gi, g in enumerate(gold) for ri, r in enumerate(reqs)), reverse=True)
    g_used, r_used, mapping = set(), set(), {}
    for score, gi, ri in pairs:
        if score < FIND_THRESHOLD:
            break
        if gi in g_used or ri in r_used:
            continue
        mapping[gi] = (ri, score)
        g_used.add(gi)
        r_used.add(ri)
    return mapping


def trap_violations(traps, kw: KeywordAnalysis, suggestions) -> List[str]:
    out = []
    for t in traps:
        if any(term_in_text(t, normalize(k)) for k in kw.missing_supported):
            out.append(f"'{t}' was offered as a keyword the CV supports")
        for s in suggestions:
            if term_in_text(t, normalize(s.suggested)) and not term_in_text(t, normalize(s.original)):
                out.append(f"'{t}' was added to a CV bullet")
    return out


def score_record(case: dict, rec: dict) -> dict:
    jd = ParsedJD.model_validate(rec["parsed_jd"])
    results = {r["requirement_id"]: MatchResult.model_validate(r) for r in rec["results"]}
    kw = KeywordAnalysis.model_validate(rec["keywords"])
    sugg = [BulletSuggestion.model_validate(s) for s in rec["suggestions"]]
    norm_md = normalize(rec.get("markdown", ""))
    mapping = map_gold(case["gold"], jd.requirements)

    rows = []
    for gi, g in enumerate(case["gold"]):
        expect = _list(g["expect"])
        row = {"case": case["id"], "requirement": g["text"], "expect": expect, "found": gi in mapping,
               "min_years": g.get("min_years"), "gold_priority": g["priority"]}
        if gi in mapping:
            req = jd.requirements[mapping[gi][0]]
            res = results.get(req.id)
            got = res.verdict.value if res else "missing"
            row.update(
                parsed=req.text, parsed_priority=req.priority.value,
                priority_ok=req.priority.value == g["priority"],
                years_ok=_years_ok(g.get("min_years"), req.min_years),
                got=got, strict_ok=got == expect[0], ok=got in expect,
                critical=got == "meets" and "meets" not in expect,
                integrity_ok=got != "meets" or bool(res and res.verified and res.evidence_snippet),
                reason=res.reason if res else "", evidence=res.evidence_snippet if res else "")
        rows.append(row)

    supported = [normalize(k) for k in kw.missing_supported]
    exp_sup = case.get("expected_supported", [])
    return {
        "case": case["id"], "title": case.get("title", ""), "rows": rows,
        "traps": trap_violations(case.get("trap_keywords", []), kw, sugg),
        "risk": trap_violations(case.get("known_risk_traps", []), kw, sugg),
        "forbidden": [f for f in case.get("forbidden_text", []) if normalize(f) in norm_md],
        "bad_numbers": [s.suggested for s in sugg
                        if not set(_NUM.findall(s.suggested)) <= set(_NUM.findall(s.original))],
        "supported_expected": exp_sup,
        "supported_hit": [k for k in exp_sup if normalize(k) in supported],
        "requests": rec.get("requests", 0), "elapsed": rec.get("elapsed", 0),
    }


def aggregate(scored: List[dict]) -> dict:
    rows = [r for s in scored for r in s["rows"]]
    found = [r for r in rows if r["found"]]

    def pct(a, b):
        return round(100 * a / b, 1) if b else None

    return {
        "cases": len(scored), "gold": len(rows), "found": len(found),
        "recall": pct(len(found), len(rows)),
        "priority_acc": pct(sum(r["priority_ok"] for r in found), len(found)),
        "years_acc": pct(sum(r["years_ok"] for r in found), len(found)),
        "strict_acc": pct(sum(r["strict_ok"] for r in found), len(found)),
        "ok_acc": pct(sum(r["ok"] for r in found), len(found)),
        "e2e_ok": pct(sum(r["ok"] for r in found), len(rows)),
        "critical": sum(r["critical"] for r in found),
        "integrity_fail": sum(not r["integrity_ok"] for r in found),
        "trap": sum(len(s["traps"]) for s in scored),
        "forbidden": sum(len(s["forbidden"]) for s in scored),
        "bad_numbers": sum(len(s["bad_numbers"]) for s in scored),
        "supported_expected": sum(len(s["supported_expected"]) for s in scored),
        "supported_hit": sum(len(s["supported_hit"]) for s in scored),
        "risk": sum(len(s["risk"]) for s in scored),
        "requests": sum(s["requests"] for s in scored),
        "confusion": Counter((r["expect"][0], r["got"]) for r in found),
    }


def collect_bugs(scored: List[dict]) -> List[dict]:
    bugs: List[dict] = []

    def add(case, what, expected, sev, comp):
        bugs.append({"id": f"B{len(bugs) + 1:02d}", "case": case, "what": what,
                     "expected": expected, "severity": sev, "component": comp})

    for s in scored:
        c = s["case"]
        for r in s["rows"]:
            q = r["requirement"]
            if not r["found"]:
                add(c, f"Requirement not found in parsed JD: {q}", "Extracted as its own requirement",
                    "Major", "JD parser")
                continue
            if not r["priority_ok"]:
                add(c, f"Priority wrong for '{q}': got {r['parsed_priority']}", r["gold_priority"],
                    "Minor", "JD parser")
            if not r["years_ok"]:
                add(c, f"min_years wrong for '{q}'", f"min_years = {r['min_years']}", "Major",
                    "JD parser (min_years)")
            if not r["integrity_ok"]:
                add(c, f"'meets' without verified evidence: {q}", "Downgrade to unclear", "Critical", "Verifier")
            if r["critical"]:
                add(c, f"False 'meets' for '{q}'", " or ".join(r["expect"]), "Critical",
                    "Matcher / years logic" if r["min_years"] else "Matcher")
            elif not r["ok"]:
                add(c, f"'{q}': got {r['got']}", " or ".join(r["expect"]), "Minor", "Matcher")
        for t in s["traps"]:
            add(c, t, "Not suggested (CV has no evidence)", "Critical", "Keyword analysis / enhancer")
        for f in s["forbidden"]:
            add(c, f"Injected CV text appears in the report: '{f}'", "Injected text ignored",
                "Critical", "Prompt-injection defence")
        for b in s["bad_numbers"]:
            add(c, f"Suggestion contains a number not in the original: {b[:80]}", "No new numbers",
                "Critical", "Enhancer guardrail")
        for t in s["risk"]:
            add(c, t, "Known limitation (alternative keyword in an OR requirement)", "Minor",
                "Keyword analysis (known limitation)")
    return bugs
