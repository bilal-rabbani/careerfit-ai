import sys

import streamlit as st

from graph import graph_a, graph_b
from graph.graph_a import ParseFailed
from graph.graph_b import AnalyzeFailed
from graph.report import ICON, LABEL
from graph.schemas import JobEntry, Priority
from llm.config import DEFAULT_MODELS
from llm.router import KeyConfig, LLMError, QuotaExhausted, test_keys
from utils import review as rv
from utils.experience import fmt_years
from utils.export import report_to_html
from utils.extract import ExtractionError, resolve_input, prepare_pasted
from utils.quota import DEMO_CAP, SESSION_STEP_CAP

st.set_page_config(page_title="CareerFit AI", page_icon="🎯", layout="wide")

esc = rv.md_escape
STEPS = ["input", "preview", "review", "report"]
TITLES = {"input": "Add your documents", "preview": "Check the text",
          "review": "Check what the AI found", "report": "Your report"}
STATUS_ICON = {"ok": "✅", "rate_limited": "🟡"}

for _k, _v in {"step": "input", "units_used": 0, "parse_id": 0, "read_id": 0, "key_test": None,
               "key_sig": None, "parse_warnings": [], "edit_warnings": []}.items():
    st.session_state.setdefault(_k, _v)


# ---------- helpers ----------
def go(step: str):
    st.session_state.step = step
    st.rerun()


def reset_data():
    for k in ("extracts", "jd_text", "cv_text", "parsed_jd", "parsed_cv", "outcome"):
        st.session_state.pop(k, None)
    st.session_state.parse_warnings = []
    st.session_state.edit_warnings = []


def friendly_error(e: Exception) -> str:
    if isinstance(e, (ExtractionError, ParseFailed, AnalyzeFailed)):
        return str(e)
    if isinstance(e, QuotaExhausted):
        return ("Every key is rate limited or was rejected. Wait a minute and try again, add a key from a "
                "different account, or use **Test keys** in the sidebar.\n\n" + str(e))
    if isinstance(e, LLMError):
        return str(e)
    print(f"Unexpected error: {type(e).__name__}", file=sys.stderr)   # type only, never the text
    return "Something unexpected went wrong. Please try again."


def run_stage(label: str, fn):
    """Runs fn() inside a progress box. Returns (result, error_message)."""
    with st.status(label, expanded=True) as status:
        st.write("Free-tier AI can be slow, and rate-limit waits can add up to about 20 seconds.")
        try:
            result = fn()
        except Exception as e:
            status.update(label="Something went wrong", state="error")
            return None, friendly_error(e)
        status.update(label="Done", state="complete", expanded=False)
    return result, None


def spend_demo_step(mode: str):
    """Returns an error message if the demo limits are hit, else None."""
    if mode != "demo":
        return None
    if st.session_state.units_used >= SESSION_STEP_CAP:
        return "Demo limit reached for this session. Add your own free API key in the sidebar to continue."
    if not DEMO_CAP.try_acquire():
        return "The shared demo quota is used up for today. Add your own free API key in the sidebar, or try again tomorrow."
    st.session_state.units_used += 1
    return None


def server_keys():
    out = []
    try:
        for provider, name in (("groq", "GROQ_API_KEY"), ("gemini", "GEMINI_API_KEY")):
            v = st.secrets.get(name)
            if v:
                out.append(KeyConfig(provider, str(v)))
    except Exception:
        pass                                  # no secrets configured
    return out


# ---------- sidebar ----------
def sidebar_keys():
    sb = st.sidebar
    sb.header("🔑 API keys")
    sb.caption("Free keys: console.groq.com/keys and aistudio.google.com/apikey. "
               "Keys stay in this browser session only. They are never saved or logged.")
    n = int(sb.number_input("Number of keys", min_value=1, max_value=6, value=1, key="n_keys"))
    keys = []
    for i in range(n):
        provider = sb.selectbox(f"Key {i + 1} provider", list(DEFAULT_MODELS), key=f"prov_{i}")
        secret = sb.text_input(f"Key {i + 1}", type="password", key=f"key_{i}")
        model = sb.text_input(f"Key {i + 1} model (optional)", key=f"model_{i}",
                              placeholder=DEFAULT_MODELS[provider]).strip()
        if not secret.strip():
            continue
        hint = rv.key_format_hint(provider, secret)
        if hint:
            sb.warning(hint)
        if model and not rv.valid_model(model):
            sb.warning("Model name has unusual characters, so the default model is used.")
            model = ""
        keys.append(KeyConfig(provider, secret, model))
    if len(keys) > 1:
        sb.caption("Several keys only add capacity if they come from different accounts or projects. "
                   "One key for everything works too.")
    sig = tuple(k.label for k in keys)
    if st.session_state.key_sig != sig:
        st.session_state.key_sig, st.session_state.key_test = sig, None
    if keys:
        if sb.button("Test keys", key="btn_test"):
            with st.spinner("Testing keys..."):
                st.session_state.key_test = test_keys(keys)
        for r in st.session_state.key_test or []:
            sb.markdown(f"{STATUS_ICON.get(r['status'], '❌')} {esc(r['label'])} {esc(r['detail'])}")
    return keys


# ---------- step 1: input ----------
def load_sample():
    from evaluation.cases import CASES
    c = next(x for x in CASES if x["id"] == "c3_civil_synonyms")     # fictional CV and job
    st.session_state["jd_paste"] = c["jd"]
    st.session_state["cv_paste"] = c["cv"]


def step_input():
    st.button("Try with a sample (fictional) CV and job", key="btn_sample", on_click=load_sample,
              help="Fills both boxes with made-up data. An uploaded file still takes priority over pasted text.")
    c1, c2 = st.columns(2)
    for col, kind, title in ((c1, "jd", "Job description"), (c2, "cv", "Your CV")):
        with col:
            st.subheader(title)
            st.file_uploader("Upload PDF, DOCX or TXT", type=["pdf", "docx", "txt"], key=f"{kind}_file")
            st.text_area("...or paste the text", height=220, key=f"{kind}_paste")
    if st.button("Read my documents", type="primary", key="btn_read"):
        results, errors = {}, []
        for kind, name in (("jd", "Job description"), ("cv", "CV")):
            f = st.session_state.get(f"{kind}_file")
            try:
                results[kind] = resolve_input(kind, st.session_state.get(f"{kind}_paste", ""),
                                              f.getvalue() if f else None, f.name if f else "")
            except ExtractionError as e:
                errors.append(f"{name}: {e}")
        if errors:
            for e in errors:
                st.error(e)
            return
        st.session_state.extracts = results
        st.session_state.read_id += 1
        go("preview")


# ---------- step 2: preview ----------
def step_preview(keys, mode):
    if "extracts" not in st.session_state:
        reset_data()
        return go("input")
    ex, rid = st.session_state.extracts, st.session_state.read_id
    for kind, name in (("jd", "Job description"), ("cv", "CV")):
        for w in ex[kind].warnings:
            st.warning(f"{name}: {esc(w)}")
    c1, c2 = st.columns(2)
    jd_text = c1.text_area("Job description text", ex["jd"].text, height=380, key=f"pv_jd_{rid}")
    cv_text = c2.text_area("CV text", ex["cv"].text, height=380, key=f"pv_cv_{rid}")
    st.caption("Fix anything the file reader got wrong (column order, missing sections). This is the text that gets analysed.")

    b1, b2, _ = st.columns([1, 2, 5])
    if b1.button("Back", key="btn_back_input"):
        reset_data()
        go("input")
    if b2.button("Parse with AI", type="primary", key="btn_parse"):
        if not keys:
            st.error("Add an API key in the sidebar first.")
            return
        try:
            jd, cv = prepare_pasted(jd_text, "jd"), prepare_pasted(cv_text, "cv")
        except ExtractionError as e:
            st.error(str(e))
            return
        msg = spend_demo_step(mode)
        if msg:
            st.error(msg)
            return
        out, err = run_stage("Reading your documents with AI...",
                             lambda: graph_a.parse_documents(jd.text, cv.text, keys))
        if err:
            st.error(err)
            return
        st.session_state.extracts = {"jd": jd, "cv": cv}      # "Back" shows the confirmed text
        st.session_state.read_id += 1
        st.session_state.jd_text, st.session_state.cv_text = jd.text, cv.text
        st.session_state.parsed_jd, st.session_state.parsed_cv = out.jd, out.cv
        st.session_state.parse_warnings = out.warnings + jd.warnings + cv.warnings
        st.session_state.parse_id += 1
        go("review")


# ---------- step 3: review ----------
def step_review(keys, mode, use_summary):
    if "parsed_jd" not in st.session_state or "parsed_cv" not in st.session_state:
        reset_data()
        return go("input")
    jd, cv, pid = st.session_state.parsed_jd, st.session_state.parsed_cv, st.session_state.parse_id
    for w in st.session_state.parse_warnings:
        st.warning(esc(w))
    st.caption("The AI can make mistakes. Fix requirements, dates and bullets here. Dates drive the years-of-experience "
               "check, so use YYYY-MM or YYYY, and 'present' for a current job.")

    tab_jd, tab_cv = st.tabs(["Job requirements", "Your CV data"])
    with tab_jd:
        title = st.text_input("Job title", jd.job_title, key=f"rv_{pid}_title")
        req_df = st.data_editor(
            rv.jd_to_frame(jd), key=f"rv_{pid}_req", num_rows="dynamic", hide_index=True,
            column_config={
                "id": st.column_config.TextColumn("ID", disabled=True),
                "text": st.column_config.TextColumn("Requirement", width="large"),
                "type": st.column_config.SelectboxColumn("Type", options=rv.TYPES),
                "priority": st.column_config.SelectboxColumn("Priority", options=rv.PRIOS),
                "min_years": st.column_config.NumberColumn("Min years", min_value=0, max_value=40, step=0.5),
                "keywords": st.column_config.TextColumn("Keywords (comma separated)")})
        st.caption("Soft skills (communication, teamwork) can't be judged from a CV and are never counted. "
                   "If a real skill was typed as soft_skill, change its type.")

    with tab_cv:
        name = st.text_input("Name", cv.name, key=f"rv_{pid}_name")
        st.markdown("**Jobs**")
        extra = st.session_state.get(f"extra_jobs_{pid}", 0)
        jobs = []
        for i in range(len(cv.jobs) + extra):
            base = cv.jobs[i] if i < len(cv.jobs) else JobEntry()
            label = f"{i + 1}. {base.title or 'New job'} ({base.start or '?'} to {base.end or '?'})"
            with st.expander(label, expanded=(i < 2 or i >= len(cv.jobs))):
                a, b = st.columns(2)
                t = a.text_input("Job title", base.title, key=f"rv_{pid}_j{i}_t")
                c = b.text_input("Company", base.company, key=f"rv_{pid}_j{i}_c")
                a, b = st.columns(2)
                s = a.text_input("Start (YYYY-MM or YYYY)", base.start, key=f"rv_{pid}_j{i}_s")
                e = b.text_input("End (YYYY-MM, YYYY or present)", base.end, key=f"rv_{pid}_j{i}_e")
                bl = st.text_area("Bullets (one per line)", rv.list_to_lines(base.bullets), height=150,
                                  key=f"rv_{pid}_j{i}_b")
                sk = st.checkbox("Ignore this job", key=f"rv_{pid}_j{i}_x")
            jobs.append({"title": t, "company": c, "start": s, "end": e, "bullets": bl, "skip": sk})
        if st.button("Add a job", key=f"btn_addjob_{pid}"):
            st.session_state[f"extra_jobs_{pid}"] = extra + 1
            st.rerun()

        st.markdown("**Education**")
        edu_df = st.data_editor(rv.edu_to_frame(cv), key=f"rv_{pid}_edu", num_rows="dynamic", hide_index=True)
        c1, c2, c3 = st.columns(3)
        skills = c1.text_area("Skills (one per line)", rv.list_to_lines(cv.skills), height=200, key=f"rv_{pid}_sk")
        certs = c2.text_area("Certifications (one per line)", rv.list_to_lines(cv.certifications),
                             height=200, key=f"rv_{pid}_ce")
        projects = c3.text_area("Projects (one per line)", rv.list_to_lines(cv.projects),
                                height=200, key=f"rv_{pid}_pr")

    b1, b2, _ = st.columns([1, 2, 5])
    if b1.button("Back", key="btn_back_preview"):
        go("preview")
    if b2.button("Run analysis", type="primary", key="btn_analyze"):
        new_jd, w1 = rv.frame_to_jd(req_df, jd, title)
        new_cv, w2 = rv.build_cv(cv, name, jobs, edu_df, skills, certs, projects)
        if not new_jd.requirements:
            st.error("Add at least one requirement to analyse.")
            return
        if not keys:
            st.error("Add an API key in the sidebar first.")
            return
        msg = spend_demo_step(mode)
        if msg:
            st.error(msg)
            return
        out, err = run_stage("Comparing your CV with the job...", lambda: graph_b.analyze(
            new_jd, new_cv, st.session_state.cv_text, keys, use_llm_summary=use_summary))
        if err:
            st.error(err)
            return
        st.session_state.parsed_jd, st.session_state.parsed_cv = new_jd, new_cv   # keep the user's edits
        st.session_state.parse_id += 1
        st.session_state.outcome = out
        st.session_state.edit_warnings = w1 + w2
        go("report")


# ---------- step 4: report ----------
def render_report(o):
    rep = o.report
    st.header("Results" + (f": {esc(rep.job_title)}" if rep.job_title else ""))
    m1, m2, m3 = st.columns(3)
    m1.metric("Must-haves met", f"{rep.must_have_met} of {rep.must_have_total}")
    exp = o.total_experience
    m2.metric("Experience from CV dates", f"{fmt_years(exp.low, exp.high)} yrs" if exp.jobs_used else "n/a")
    m3.metric("Keywords you can add", len(rep.keywords.missing_supported))
    if rep.summary:
        st.info(esc(rep.summary))
    for w in o.warnings + st.session_state.edit_warnings:
        st.warning(esc(w))

    st.subheader("Requirement analysis")
    for r in rep.rows:
        tag = "must-have" if r.priority == Priority.MUST_HAVE else "nice-to-have"
        with st.container(border=True):
            st.markdown(f"{ICON[r.verdict]} **{esc(r.requirement)}**")
            st.caption(f"{tag} · {LABEL[r.verdict]}")
            if r.reason:
                st.markdown(esc(r.reason))
            if r.evidence:
                st.markdown(f"> {esc(r.evidence)}")
                if r.verified:
                    st.caption("✔ Verified against your CV")

    kw = rep.keywords
    st.subheader("Keyword analysis")
    st.markdown("**Already in your CV:** " + (", ".join(esc(k) for k in kw.present) or "none"))
    if kw.missing_supported:
        st.markdown("**Your CV supports these but uses different wording. Consider the job's exact terms:**")
        for k in kw.missing_supported:
            ev = o.kw_evidence.get(k)
            st.markdown(f"- {esc(k)}" + (f" — your CV says: “{esc(ev)[:140]}”" if ev else ""))
    if kw.missing_unsupported:
        st.markdown("**Not supported by your CV. Add only if you truly have this experience:**")
        for k in kw.missing_unsupported:
            st.markdown(f"- {esc(k)}")

    if rep.suggestions:
        st.subheader("Suggested CV wording")
        st.caption("Suggestions only. Check that every word is true before you use it.")
        for s in rep.suggestions:
            with st.container(border=True):
                a, b = st.columns(2)
                a.caption("Original")
                a.markdown(esc(s.original))
                b.caption("Suggested (use the copy button)")
                b.code(s.suggested, language=None)
                st.caption("Keywords: " + ", ".join(s.keywords_used))

    st.subheader("Download")
    d1, d2, _ = st.columns([1, 1, 3])
    d1.download_button("Markdown (.md)", o.markdown, "careerfit_report.md", "text/markdown", key="dl_md")
    d2.download_button("HTML (print to PDF)", report_to_html(rep, o.kw_evidence, o.warnings),
                       "careerfit_report.html", "text/html", key="dl_html")


def step_report():
    if "outcome" not in st.session_state:
        reset_data()
        return go("input")
    render_report(st.session_state.outcome)
    b1, b2, _ = st.columns([1, 1, 5])
    if b1.button("Edit and re-run", key="btn_edit"):
        go("review")
    if b2.button("Start over", key="btn_restart"):
        reset_data()
        go("input")


# ---------- page ----------
user_keys = sidebar_keys()
if user_keys:
    keys, mode = user_keys, "user"
else:
    keys = server_keys()
    mode = "demo" if keys else "none"
if mode == "demo":
    left = max(0, SESSION_STEP_CAP - st.session_state.units_used)
    st.sidebar.info(f"Demo mode (shared key). {left} step(s) left this session; an analysis uses 2. "
                    "Add your own key for unlimited use.")
elif mode == "none":
    st.sidebar.warning("Add at least one API key to start.")
use_summary = st.sidebar.checkbox("AI-written summary (1 extra call)", key="use_summary")

st.title("🎯 CareerFit AI")
st.caption("Match Your Skills. Improve Your CV. Apply with Confidence.")
st.caption("🔒 Your CV and job text are sent to the AI provider whose key is used. Some free tiers may use submitted text "
           "to improve their products, so check their terms and leave out ID numbers. This app never saves your files; "
           "results stay in memory for up to an hour to avoid repeat API calls.")

with st.expander("How this works and its limits"):
    st.markdown(
        "- The AI reads the job description and your CV and splits them into requirements and facts.\n"
        "- You **review and correct** what it found before anything is judged.\n"
        "- Each requirement gets **Meets / No clear evidence / Does not meet / Can't be judged from a CV**.\n"
        "- A **Meets** verdict needs a quote from your CV. Code checks that the quote really exists in your text. "
        "That proves the quote is real, not that it fully satisfies the requirement, so read the evidence yourself.\n"
        "- Years of experience are calculated by code from your job dates, not guessed by the AI.\n"
        "- A keyword is only suggested when your CV already supports it. Anything else is listed as "
        "*add only if you truly have this*.\n"
        "- **Limits:** scanned PDFs can't be read (paste the text instead). Soft skills are never scored. "
        "Requirements like *Salesforce or HubSpot* can be matched through either option. "
        "Free AI models can make mistakes, so treat the result as a guide, not a verdict.")

step = st.session_state.step
idx = STEPS.index(step)
st.progress((idx + 1) / len(STEPS), text=f"Step {idx + 1} of {len(STEPS)}: {TITLES[step]}")

if step == "input":
    step_input()
elif step == "preview":
    step_preview(keys, mode)
elif step == "review":
    step_review(keys, mode, use_summary)
else:
    step_report()
