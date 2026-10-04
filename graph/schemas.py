from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, field_validator

LEVELS = ["basic", "intermediate", "advanced", "professional"]
CLAIMS = ["strong", "partial", "weak", "none"]


def norm_level(v) -> str:
    s = str(v or "").strip().lower()
    return s if s in LEVELS else ""


def norm_claim(v) -> str:
    s = str(v or "").strip().lower()
    return s if s in CLAIMS else ""


# ---------- Enums ----------
class Verdict(str, Enum):
    MEETS = "meets"
    UNCLEAR = "unclear"
    DOES_NOT_MEET = "does_not_meet"
    CANNOT_ASSESS = "cannot_assess"


class Priority(str, Enum):
    MUST_HAVE = "must_have"
    NICE_TO_HAVE = "nice_to_have"


class ReqType(str, Enum):
    EDUCATION = "education"
    EXPERIENCE = "experience"
    SKILL = "skill"
    TOOL = "tool"
    CERTIFICATION = "certification"
    SOFT_SKILL = "soft_skill"
    OTHER = "other"


class Strength(str, Enum):
    STRONG = "strong"
    PARTIAL = "partial"
    WEAK = "weak"
    NONE = "none"
    UNAVAILABLE = "unavailable"


class Fix(str, Enum):
    NONE = "none"
    CV_FIXABLE = "cv_fixable"
    TRAINABLE = "trainable"
    GENUINE_GAP = "genuine_gap"


# ---------- Parsed Job Description ----------
class JDRequirement(BaseModel):
    id: str = Field(default="", description="Assigned by code, leave empty")
    text: str = Field(description="One requirement, short and specific")
    type: ReqType = ReqType.OTHER
    priority: Priority = Priority.MUST_HAVE
    min_years: Optional[float] = Field(default=None, description="Years required, if stated")
    required_level: str = Field(default="", description="basic, intermediate, advanced or professional, only if the wording states it; else empty")
    keywords: List[str] = Field(default_factory=list, description="Key terms for this requirement")

    @field_validator("required_level", mode="before")
    @classmethod
    def _clean_level(cls, v):
        return norm_level(v)


class ParsedJD(BaseModel):
    job_title: str = ""
    requirements: List[JDRequirement] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list, description="Important terms across the whole JD")


# ---------- Parsed CV ----------
class JobEntry(BaseModel):
    title: str = ""
    company: str = ""
    start: str = Field(default="", description="YYYY-MM or YYYY")
    end: str = Field(default="", description="YYYY-MM, YYYY, or 'present'")
    bullets: List[str] = Field(default_factory=list)


class EducationEntry(BaseModel):
    degree: str = ""
    field: str = ""
    institution: str = ""
    year: str = ""


class ParsedCV(BaseModel):
    name: str = ""
    education: List[EducationEntry] = Field(default_factory=list)
    jobs: List[JobEntry] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)
    projects: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list, description="Terms present in the CV")


# ---------- Matching ----------
class MatchResult(BaseModel):
    requirement_id: str
    verdict: Verdict
    evidence_snippet: str = Field(default="", description="Exact text copied from the CV. Empty if none.")
    reason: str = Field(default="", description="One short sentence")
    verified: bool = Field(default=False, description="Set by code, not the LLM")
    strength: Strength = Strength.NONE
    fix: Fix = Fix.NONE
    cv_level: str = ""
    level_gap: bool = False


class MatcherOutput(BaseModel):
    results: List[MatchResult] = Field(default_factory=list)


# ---------- Keywords and enhancement ----------
class KeywordGroup(BaseModel):
    requirement: str = ""
    present: List[str] = Field(default_factory=list)
    supported: List[str] = Field(default_factory=list)
    unsupported: List[str] = Field(default_factory=list)


class KeywordAnalysis(BaseModel):
    present: List[str] = Field(default_factory=list)
    missing_supported: List[str] = Field(default_factory=list)
    missing_unsupported: List[str] = Field(default_factory=list)
    groups: List[KeywordGroup] = Field(default_factory=list)


class BulletSuggestion(BaseModel):
    original: str
    suggested: str
    keywords_used: List[str] = Field(default_factory=list)
    job: str = ""


class EnhancerOutput(BaseModel):
    suggestions: List[BulletSuggestion] = Field(default_factory=list)


# ---------- Final report ----------
class ReportRow(BaseModel):
    requirement: str
    type: str = "other"
    priority: Priority
    verdict: Verdict
    evidence: str = ""
    reason: str = ""
    verified: bool = False
    strength: Strength = Strength.NONE
    fix: Fix = Fix.NONE
    required_level: str = ""
    cv_level: str = ""
    where: str = ""


class Report(BaseModel):
    job_title: str = ""
    rows: List[ReportRow] = Field(default_factory=list)
    must_have_met: int = 0
    must_have_total: int = 0
    keywords: KeywordAnalysis = Field(default_factory=KeywordAnalysis)
    suggestions: List[BulletSuggestion] = Field(default_factory=list)
    summary: str = ""
    fix_counts: Dict[str, int] = Field(default_factory=dict)


def assign_ids(jd: ParsedJD) -> ParsedJD:
    """Give each requirement a stable id like R1, R2..."""
    for i, req in enumerate(jd.requirements, start=1):
        req.id = f"R{i}"
    return jd
