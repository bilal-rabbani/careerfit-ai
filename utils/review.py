import re
from typing import Dict, List, Tuple

import pandas as pd

from graph.parsers import MAX_REQS
from graph.schemas import (ParsedJD, ParsedCV, JDRequirement, JobEntry, EducationEntry,
                           ReqType, Priority, assign_ids)
from utils.experience import years_of_experience
from utils.textnorm import normalize

TYPES = [t.value for t in ReqType]
PRIOS = [p.value for p in Priority]
LEVEL_OPTIONS = ["none", "basic", "intermediate", "advanced", "professional"]
MAX_JOBS, MAX_BULLETS = 12, 12
REQ_COLS = ["id", "text", "type", "priority", "min_years", "level", "keywords"]
EDU_COLS = ["degree", "field", "institution", "year"]

_BULLET = re.compile(r"^\s*(?:[-*•●▪◦]|\d+[.)])\s+")
_MODEL = re.compile(r"^[A-Za-z0-9._-]{1,80}$")
_PUNCT = re.compile(r"([!-/:-@\[-`{-~])")        # every ASCII punctuation character


# ---------- small cleaners ----------
def _s(v) -> str:
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except (TypeError, ValueError):
        pass
    return " ".join(str(v).split())


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def list_to_lines(items: List[str]) -> str:
    return "\n".join(items)


def lines_to_list(text: str, limit: int, split_commas: bool = False) -> List[str]:
    parts = re.split(r"[\n,;]" if split_commas else r"\n", text or "")
    out, seen = [], set()
    for p in parts:
        p = _BULLET.sub("", p).strip()
        k = p.lower()
        if p and k not in seen:
            seen.add(k)
            out.append(p)
    return out[:limit]


# ---------- Job description <-> table ----------
def jd_to_frame(jd: ParsedJD) -> pd.DataFrame:
    rows = [{"id": r.id, "text": r.text, "type": r.type.value, "priority": r.priority.value,
             "min_years": r.min_years, "level": r.required_level or "none", "keywords": ", ".join(r.keywords)} for r in jd.requirements]
    df = pd.DataFrame(rows, columns=REQ_COLS)
    df["min_years"] = pd.to_numeric(df["min_years"], errors="coerce")
    return df


def frame_to_jd(df: pd.DataFrame, base: ParsedJD, job_title: str = "") -> Tuple[ParsedJD, List[str]]:
    warnings, reqs, seen, dupes = [], [], set(), 0
    for row in df.to_dict("records"):
        text = _s(row.get("text"))[:200]
        if not text:
            continue
        key = normalize(text)
        if key in seen:
            dupes += 1
            continue
        seen.add(key)
        typ = _s(row.get("type")).lower()
        pri = _s(row.get("priority")).lower()
        yrs = _num(row.get("min_years"))
        kws, kseen = [], set()
        for k in re.split(r"[,;]", _s(row.get("keywords"))):
            k = k.strip()
            if k and len(k) <= 40 and k.lower() not in kseen:
                kseen.add(k.lower())
                kws.append(k)
        reqs.append(JDRequirement(
            text=text,
            type=typ if typ in TYPES else "other",
            priority=pri if pri in PRIOS else "must_have",
            min_years=yrs if yrs and 0 < yrs <= 40 else None,
            required_level=_s(row.get("level")).lower() if typ in ("skill", "tool") else "",
            keywords=kws[:5]))
    if dupes:
        warnings.append(f"{dupes} duplicate requirement(s) were removed.")
    if len(reqs) > MAX_REQS:
        warnings.append(f"Only the first {MAX_REQS} requirements are analysed.")
        reqs = reqs[:MAX_REQS]
    jd = ParsedJD(job_title=_s(job_title)[:120], requirements=reqs, keywords=list(base.keywords))
    return assign_ids(jd), warnings


# ---------- CV <-> widgets ----------
def edu_to_frame(cv: ParsedCV) -> pd.DataFrame:
    return pd.DataFrame([e.model_dump() for e in cv.education], columns=EDU_COLS)


def build_cv(base: ParsedCV, name: str, jobs: List[Dict], edu_df: pd.DataFrame,
             skills_text: str, certs_text: str, projects_text: str) -> Tuple[ParsedCV, List[str]]:
    warnings, out_jobs = [], []
    for j in jobs:
        if j.get("skip"):
            continue
        title, company, start, end = (_s(j.get(k)) for k in ("title", "company", "start", "end"))
        bullets = lines_to_list(j.get("bullets", ""), MAX_BULLETS)
        if not (title or company or bullets):
            continue
        out_jobs.append(JobEntry(title=title[:120], company=company[:120], start=start[:20],
                                 end=end[:20], bullets=[b[:500] for b in bullets]))
    if len(out_jobs) > MAX_JOBS:
        warnings.append(f"Only the first {MAX_JOBS} jobs are analysed.")
        out_jobs = out_jobs[:MAX_JOBS]
    undated = sum(1 for j in out_jobs if years_of_experience([j]).jobs_used == 0)
    if undated:
        warnings.append(f"{undated} job(s) have no readable dates, so years of experience can't be fully "
                        f"calculated. Use YYYY-MM or YYYY, and 'present' for a current job.")
    edu = []
    for row in edu_df.to_dict("records"):
        vals = {c: _s(row.get(c))[:120] for c in EDU_COLS}
        if any(vals.values()):
            edu.append(EducationEntry(**vals))
    cv = ParsedCV(name=_s(name)[:120], education=edu, jobs=out_jobs,
                  skills=lines_to_list(skills_text, 60, split_commas=True),
                  certifications=lines_to_list(certs_text, 20),
                  projects=lines_to_list(projects_text, 10),
                  keywords=list(base.keywords))
    return cv, warnings


# ---------- Keys ----------
def key_format_hint(provider: str, key: str) -> str:
    k = (key or "").strip()
    if not k:
        return ""
    if any(c.isspace() for c in k):
        return "This key contains spaces. Copy it again."
    return ""


def valid_model(m: str) -> bool:
    return bool(_MODEL.match((m or "").strip()))


# ---------- Safe display ----------
def md_escape(s) -> str:
    """Make arbitrary text render literally in st.markdown (no maths, links, colours, emoji codes)."""
    return _PUNCT.sub(r"\\\1", " ".join(str(s or "").split()))
