import html
from typing import Dict, List, Optional

from graph.report import GROUP_TITLE, GROUP_NOTE, LEGEND, group_rows, row_parts
from graph.schemas import Report, Verdict

COLORS = {Verdict.MEETS: "#2e9e5b", Verdict.UNCLEAR: "#d9a400",
          Verdict.DOES_NOT_MEET: "#d64545", Verdict.CANNOT_ASSESS: "#9aa0a6"}

CSS = """<style>
body{font-family:system-ui,Arial,sans-serif;line-height:1.5;color:#1f2328;margin:0;background:#fff}
main{max-width:820px;margin:0 auto;padding:24px}
h1{font-size:1.6rem}h2{font-size:1.2rem;margin-top:2rem;border-bottom:1px solid #ddd;padding-bottom:4px}
h3{font-size:1.05rem;margin:1.4rem 0 .2rem}
.row{border-left:5px solid #ccc;padding:6px 12px;margin:8px 0;background:#f8f9fa;break-inside:avoid}
.meta{color:#57606a;font-size:.9rem}.quote{font-style:italic}
.pair{border:1px solid #ddd;padding:8px 12px;margin:10px 0;break-inside:avoid}
.note{background:#fff8e1;padding:8px 12px}
@media print{main{max-width:none;padding:0}}
</style>"""


def _e(s) -> str:
    return html.escape(" ".join(str(s or "").split()))


def _row_html(r) -> str:
    p = row_parts(r)
    meta = f"{p['tag']} · {p['strength']}" + (f" · {p['level']}" if p["level"] else "")
    h = [f"<div class='row' style='border-left-color:{COLORS[r.verdict]}'>",
         f"<div>{p['icon']} <strong>{_e(p['title'])}</strong> <span class='meta'>({_e(meta)})</span></div>"]
    if p["reason"]:
        h.append(f"<div>{_e(p['reason'])}</div>")
    if p["quote"]:
        h.append(f"<div class='quote'>Your CV says: “{_e(p['quote'])}”</div>")
    if p["where"]:
        h.append(f"<div class='meta'>Add it to: {_e(p['where'])}</div>")
    h.append("</div>")
    return "".join(h)


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
    h.append(f"<p class='meta'>{_e(LEGEND)}</p><h2>Requirement analysis</h2>")

    g = group_rows(rep)
    for key in ("gap", "train", "fix"):
        if g[key]:
            h.append(f"<h3>{_e(GROUP_TITLE[key])}</h3><p class='meta'>{_e(GROUP_NOTE[key])}</p>")
            h += [_row_html(r) for r in g[key]]
    if g["met"]:
        h.append("<h3>Met</h3>")
        h += [_row_html(r) for r in g["met"]]
    if g["na"]:
        h.append(f"<h3>{_e(GROUP_TITLE['na'])}</h3><p>{_e('; '.join(r.requirement for r in g['na']))}</p>")

    kw = rep.keywords
    h.append("<h2>Keyword analysis</h2>")
    h.append(f"<p><strong>Already in your CV:</strong> {_e(', '.join(kw.present)) or 'none'}</p>")
    sup = [x for x in kw.groups if x.supported]
    if sup:
        h.append("<p><strong>Your CV supports these but words them differently. Consider the job's wording:</strong></p><ul>")
        for x in sup:
            ev = next((kw_evidence.get(t) for t in x.supported if kw_evidence.get(t)), "")
            h.append(f"<li>{_e(', '.join(x.supported))} <span class='meta'>(for: {_e(x.requirement[:80])})"
                     + (f" your CV says: “{_e(ev)[:120]}”" if ev else "") + "</span></li>")
        h.append("</ul>")
    elif kw.missing_supported:
        h.append(f"<p><strong>Your CV supports these but words them differently:</strong> {_e(', '.join(kw.missing_supported))}</p>")
    if kw.missing_unsupported:
        h.append("<p><strong>Not supported by your CV. Add only if you truly have this experience:</strong> "
                 f"{_e(', '.join(kw.missing_unsupported))}</p>")

    if rep.suggestions:
        h.append("<h2>Suggested CV wording</h2><p class='note'>Suggestions only. Check that every word is true before you use it.</p>")
        for s in rep.suggestions:
            h.append(f"<div class='pair'><div><strong>Original:</strong> {_e(s.original)}"
                     + (f" <span class='meta'>({_e(s.job)})</span>" if s.job else "") + "</div>"
                     f"<div><strong>Suggested:</strong> {_e(s.suggested)}</div>"
                     f"<div class='meta'>Keywords: {_e(', '.join(s.keywords_used))}</div></div>")
    if warnings:
        h.append("<h2>Notes</h2><ul>" + "".join(f"<li>{_e(w)}</li>" for w in warnings) + "</ul>")
    h.append("</main></body></html>")
    return "".join(h)
