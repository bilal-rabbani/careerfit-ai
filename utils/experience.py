import re
from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Sequence, Tuple

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
PRESENT_WORDS = ("present", "current", "now", "ongoing", "till date", "to date", "today")


@dataclass
class Experience:
    low: float = 0.0       # conservative estimate (years)
    high: float = 0.0      # generous estimate (differs when dates are year-only)
    undated: int = 0       # jobs with missing or unusable dates (not counted)
    jobs_used: int = 0


def parse_date(s: str) -> Optional[Tuple[int, Optional[int]]]:
    """Returns (year, month or None). None if unreadable."""
    s = (s or "").strip().lower()
    if not s:
        return None
    m = re.search(r"\b((?:19|20)\d{2})[-/.](\d{1,2})\b", s)           # 2023-05
    if m and 1 <= int(m.group(2)) <= 12:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"\b(\d{1,2})[/.-]((?:19|20)\d{2})\b", s)           # 05/2023
    if m and 1 <= int(m.group(1)) <= 12:
        return int(m.group(2)), int(m.group(1))
    y = re.search(r"\b((?:19|20)\d{2})\b", s)
    if not y:
        return None
    mon = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", s)
    return int(y.group(1)), (MONTHS[mon.group(1)] if mon else None)


def _idx(year: int, month: int) -> int:
    return year * 12 + month - 1


def _interval(job, today: date, scenario: str) -> Optional[Tuple[int, int]]:
    """Month interval [start, end) for one job. scenario: 'low' or 'high'."""
    start = parse_date(job.start)
    if start is None:
        return None
    sy, sm = start
    cur = _idx(today.year, today.month)
    s_idx = _idx(sy, sm) if sm else _idx(sy, 12 if scenario == "low" else 1)

    end_raw = (job.end or "").strip().lower()
    if any(w in end_raw for w in PRESENT_WORDS):
        e_idx = cur
    else:
        end = parse_date(job.end)
        if end is None:
            return None
        ey, em = end
        if ey < sy:
            return None                                   # reversed dates = data error
        e_idx = _idx(ey, em) if em else _idx(ey, 1 if scenario == "low" else 12)
        e_idx = min(e_idx, cur)
    if e_idx < s_idx:
        return (s_idx, s_idx) if scenario == "low" else None
    return (s_idx, e_idx + 1)                             # end month counts as worked


def _union_months(intervals: List[Tuple[int, int]]) -> int:
    total, cs, ce = 0, None, None
    for s, e in sorted(i for i in intervals if i[1] > i[0]):
        if ce is None or s > ce:
            if ce is not None:
                total += ce - cs
            cs, ce = s, e
        else:
            ce = max(ce, e)                               # overlapping jobs counted once
    if ce is not None:
        total += ce - cs
    return total


def years_of_experience(jobs: Sequence, today: Optional[date] = None) -> Experience:
    today = today or date.today()
    low_iv, high_iv, undated = [], [], 0
    for job in jobs:
        hi = _interval(job, today, "high")
        if hi is None:
            undated += 1
            continue
        lo = _interval(job, today, "low")
        high_iv.append(hi)
        low_iv.append(lo or (hi[0], hi[0]))
    return Experience(
        low=round(_union_months(low_iv) / 12, 2),
        high=round(_union_months(high_iv) / 12, 2),
        undated=undated, jobs_used=len(high_iv),
    )


def fmt_years(low: float, high: float) -> str:
    return f"{low:.1f}" if high - low < 0.25 else f"{low:.1f}–{high:.1f}"
