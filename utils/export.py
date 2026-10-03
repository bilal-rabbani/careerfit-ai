import html
from typing import Dict, List, Optional

from graph.report import ICON, LABEL
from graph.schemas import Report, Priority, Verdict

COLORS = {Verdict.MEETS: "#2e9e5b", Verdict.UNCLEAR: "#d9a400",
          Verdict.DOES_NOT_MEET: "#d64545", Verdict.CANNOT_ASSESS: "#9aa0a6"}

CSS = """<style>
body{font-family:system-ui,Arial,sans-serif;line-height:1.5;color:#1f2328;margin:0;background:#fff}
main{max-width:820px;margin:0 auto;padding:24px}
h1{font-size:1.6rem}h2{font-size:1.2rem;margin-top:2rem;border-bottom:1px solid #ddd;padding-bottom:4px}
.row{border-left:5px solid #ccc;padding:6px 12px;margin:10px 0;background:#f8f9fa;break-inside:avoid}
.meta{color:#57606a;font-size:.9rem}.quote{color:#1f2328;font-style:italic}
.pair{border:1px solid #ddd;padding:8px 12px;margin:10px 0;break-inside:avoid}
.note{background:#fff8e1;padding:8px 12px}
@media print{main{max-width:none;padding:0}}
</style>"""


def _e(s) -> str:
    return html.escape(" ".join(str(s or "").split()))


def report_to_html(rep: Report, kw_evidence: Optional[Dict[str, str]] = None,
                   warnings: Optional[List[str]] = None) -> str:
    kw_evidence = kw_evidence or {}
    title = "CareerFit AI report" + (f": {_e(rep.job_title)}" if rep.job_title else "")
    h = ["<!doctype html><html lang='en'><head><meta charset='utf-8'>",
         "<meta name='viewport' content='width=device-width, initial-scale=1'>",
         f"<title>{title}</title>", CSS, "</head><body><main>", f"<h1>{title}</h1>"]
    if rep.summary:
        h.append(f"<p>{_e(rep.summary)}</p>")
    h.append(f"<p><strong>Must-have requirements met: {rep.must_have_met} of {rep.must_have_total}</strong></p>")

    h.append("<h2>Requirement analysis</h2>")
    for r in rep.rows:
        tag = "must-have" if r.priority == Priority.MUST_HAVE else "nice-to-have"
        h.append(f"<div class='row' style='border-left-color:{COLORS[r.verdict]}'>"
                 f"<div>{ICON[r.verdict]} <strong>{_e(r.requirement)}</strong></div>"
                 f"<div class='meta'>{tag} · {_e(LABEL[r.verdict])}</div>")
        if r.reason:
            h.append(f"<div>{_e(r.reason)}</div>")
        if r.evidence:
            h.append(f"<div class='quote'>Evidence from your CV: “{_e(r.evidence)}”</div>")
        h.append("</div>")

    kw = rep.keywords
    h.append("<h2>Keyword analysis</h2>")
    h.append(f"<p><strong>Already in your CV:</strong> {_e(', '.join(kw.present)) or 'none'}</p>")
    if kw.missing_supported:
        h.append("<p><strong>Your CV supports these but uses different wording. Consider the job's exact terms:</strong></p><ul>")
        for k in kw.missing_supported:
            ev = kw_evidence.get(k)
            h.append(f"<li>{_e(k)}" + (f" <span class='meta'>(your CV says: “{_e(ev)[:120]}”)</span>" if ev else "") + "</li>")
        h.append("</ul>")
    if kw.missing_unsupported:
        h.append("<p><strong>Not supported by your CV. Add only if you truly have this experience:</strong></p><ul>")
        h += [f"<li>{_e(k)}</li>" for k in kw.missing_unsupported]
        h.append("</ul>")

    if rep.suggestions:
        h.append("<h2>Suggested CV wording</h2><p class='note'>Suggestions only. Check that every word is true before you use it.</p>")
        for s in rep.suggestions:
            h.append(f"<div class='pair'><div><strong>Original:</strong> {_e(s.original)}</div>"
                     f"<div><strong>Suggested:</strong> {_e(s.suggested)}</div>"
                     f"<div class='meta'>Keywords: {_e(', '.join(s.keywords_used))}</div></div>")
    if warnings:
        h.append("<h2>Notes</h2><ul>" + "".join(f"<li>{_e(w)}</li>" for w in warnings) + "</ul>")
    h.append("</main></body></html>")
    return "".join(h)
