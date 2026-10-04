from datetime import date
from typing import Dict, List

from evaluation.score import aggregate, collect_bugs

COLS = ["meets", "unclear", "does_not_meet", "cannot_assess", "missing"]


def _c(x) -> str:
    return " ".join(str("" if x is None else x).split()).replace("|", "/")


def _pct(v):
    return "n/a" if v is None else f"{v}%"


def render_bug_table(bugs: List[Dict]) -> str:
    if not bugs:
        return "No issues were detected automatically in this run.\n"
    L = ["| ID | Case | What happened | Expected | Severity | Component | Status | Fix / notes |",
         "|---|---|---|---|---|---|---|---|"]
    for b in bugs:
        L.append(f"| {b['id']} | {_c(b['case'])} | {_c(b['what'])} | {_c(b['expected'])} | "
                 f"{b['severity']} | {_c(b['component'])} | Open | |")
    return "\n".join(L) + "\n"


def render_results(scored, cases_all, label, models) -> str:
    agg, bugs = aggregate(scored), collect_bugs(scored)
    ge = lambda v, t: "pass" if v is not None and v >= t else "BELOW TARGET"
    zero = lambda n: "pass" if n == 0 else "FIX"

    L = [f"# CareerFit AI evaluation ({_c(label)})", "",
         f"Date: {date.today().isoformat()} | Models: {_c(models)} | Cases: {agg['cases']} | "
         f"Gold requirements: {agg['gold']} | LLM requests: {agg['requests']}", "",
         "All cases are synthetic, hand-written and hand-labelled. With this few requirements, one change moves a "
         "percentage a lot, so read the numbers as a rough guide, not a benchmark. The targets are working goals "
         "I chose, not industry standards.", "",
         "## Summary", "", "| Metric | Result | Target | |", "|---|---|---|---|"]
    rows = [
        ("Requirements found by the JD parser", _pct(agg["recall"]), ">= 90%", ge(agg["recall"], 90)),
        ("Priority correct (must vs nice)", _pct(agg["priority_acc"]), ">= 90%", ge(agg["priority_acc"], 90)),
        ("Years requirement correct", _pct(agg["years_acc"]), ">= 95%", ge(agg["years_acc"], 95)),
        ("Verdict acceptable (of found)", _pct(agg["ok_acc"]), ">= 85%", ge(agg["ok_acc"], 85)),
        ("Verdict exactly the ideal one (of found)", _pct(agg["strict_acc"]), "info", ""),
        ("End to end acceptable (of all gold)", _pct(agg["e2e_ok"]), "info", ""),
        ("Critical errors: false 'meets'", agg["critical"], "0", zero(agg["critical"])),
        ("'Meets' without verified evidence", agg["integrity_fail"], "0", zero(agg["integrity_fail"])),
        ("Trap keywords wrongly suggested", agg["trap"], "0", zero(agg["trap"])),
        ("Injected text echoed in the report", agg["forbidden"], "0", zero(agg["forbidden"])),
        ("Suggestions with invented numbers", agg["bad_numbers"], "0", zero(agg["bad_numbers"])),
        ("Expected keyword suggestions produced",
         f"{agg['supported_hit']} of {agg['supported_expected']}", "info", ""),
        ("Known-limitation probes triggered", agg["risk"], "info", ""),
    ]
    for name, val, target, flag in rows:
        L.append(f"| {name} | {val} | {target} | {flag} |")

    L += ["", "## Per case", "",
          "| Case | Found | Verdict OK | Critical | Keyword/safety issues | Requests | Seconds |",
          "|---|---|---|---|---|---|---|"]
    for s in scored:
        f = [r for r in s["rows"] if r["found"]]
        issues = len(s["traps"]) + len(s["forbidden"]) + len(s["bad_numbers"])
        L.append(f"| {_c(s['case'])} | {len(f)}/{len(s['rows'])} | {sum(r['ok'] for r in f)}/{len(f)} | "
                 f"{sum(r['critical'] for r in f)} | {issues} | {s['requests']} | {s['elapsed']:.0f} |")

    L += ["", "## Verdicts: expected (rows) vs got (columns)", "",
          "Expected is the first, ideal verdict listed for each requirement.", "",
          "| expected / got | " + " | ".join(COLS) + " |", "|---|" + "---|" * len(COLS)]
    for exp in COLS[:4]:
        L.append(f"| {exp} | " + " | ".join(str(agg["confusion"].get((exp, g), 0)) for g in COLS) + " |")

    not_run = [c["id"] for c in cases_all if c["id"] not in {s["case"] for s in scored}]
    if not_run:
        L += ["", "## Cases not run", "", ", ".join(not_run)]
    L += ["", "## Bug report (auto-detected)", "", render_bug_table(bugs)]
    return "\n".join(L) + "\n"
