from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, TypedDict

from langgraph.graph import StateGraph, START, END

from graph.schemas import (ParsedJD, ParsedCV, JDRequirement, MatchResult, KeywordAnalysis,
                           BulletSuggestion, Report)
from graph import matcher, verify, keywords, enhancer
from graph import report as report_mod
from llm.router import LLMError, KeyConfig
from utils.experience import Experience, years_of_experience


class AnalyzeFailed(Exception):
    """Message is safe to show to the user."""


class AnalyzeState(TypedDict, total=False):
    jd: ParsedJD
    cv: ParsedCV
    cv_text: str
    today: date
    group_a: List[JDRequirement]
    group_b: List[JDRequirement]
    matches_a: list
    matches_b: list
    a_error: str
    b_error: str
    results: List[MatchResult]
    total_experience: Experience
    kw: KeywordAnalysis
    kw_evidence: Dict[str, str]
    suggestions: List[BulletSuggestion]
    report: Report
    summary: str
    warnings: List[str]


def make_graph_b(keys: List[KeyConfig], use_llm_summary: bool = False):
    """Keys live in the closure, never in graph state."""

    def prepare(state: AnalyzeState):
        _, a, b = matcher.split_requirements(state["jd"])
        return {"group_a": a, "group_b": b,
                "total_experience": years_of_experience(state["cv"].jobs, state.get("today"))}

    def make_matcher_node(node, group_key, out_key, err_key):
        def run(state: AnalyzeState):
            group = state.get(group_key) or []
            if not group:
                return {out_key: []}
            try:
                return {out_key: matcher.run_matcher(node, group, state["cv"], state["cv_text"], keys)}
            except LLMError as e:
                return {err_key: str(e)}
        return run

    def verify_node(state: AnalyzeState):
        if state.get("a_error") or state.get("b_error"):
            return {}
        matches = state.get("matches_a", []) + state.get("matches_b", [])
        return {"results": verify.finalize_results(
            state["jd"].requirements, matches, state["cv"], state["cv_text"], state.get("today"))}

    def keyword_node(state: AnalyzeState):
        if not state.get("results"):
            return {}
        kw, ev = keywords.analyze_keywords(state["jd"], state["results"], state["cv_text"])
        return {"kw": kw, "kw_evidence": ev}

    def enhancer_node(state: AnalyzeState):
        kw = state.get("kw")
        if kw is None:
            return {}
        supported = kw.missing_supported[:enhancer.MAX_KEYWORDS]
        if not supported or not enhancer.numbered_bullets(state["cv"]):
            return {"suggestions": []}                       # nothing safe to suggest: no LLM call
        try:
            return {"suggestions": enhancer.suggest_improvements(
                state["cv"], supported, state["kw_evidence"], keys)}
        except LLMError as e:                                # non-fatal
            msg = f"Bullet suggestions couldn't be generated ({e}). The rest of the report is complete."
            return {"suggestions": [], "warnings": state.get("warnings", []) + [msg]}

    def report_node(state: AnalyzeState):
        if not state.get("results"):
            return {}
        return {"report": report_mod.build_report(
            state["jd"], state["results"], state["kw"], state.get("suggestions", []))}

    def summary_node(state: AnalyzeState):
        rep = state.get("report")
        if rep is None:
            return {}
        warns, text = state.get("warnings", []), ""
        if use_llm_summary:
            try:
                text = report_mod.llm_summary(rep, keys)
            except LLMError:
                warns = warns + ["The AI summary was unavailable, so a standard summary is shown."]
        text = text or report_mod.template_summary(rep)
        rep.summary = text
        return {"report": rep, "summary": text, "warnings": warns}

    g = StateGraph(AnalyzeState)
    g.add_node("prepare", prepare)
    g.add_node("matcher_a", make_matcher_node("matcher_a", "group_a", "matches_a", "a_error"))
    g.add_node("matcher_b", make_matcher_node("matcher_b", "group_b", "matches_b", "b_error"))
    g.add_node("verify", verify_node)
    g.add_node("keyword_analyzer", keyword_node)
    g.add_node("enhancer", enhancer_node)
    g.add_node("report_builder", report_node)
    g.add_node("summary", summary_node)
    g.add_edge(START, "prepare")
    g.add_edge("prepare", "matcher_a")                       # matchers run in parallel
    g.add_edge("prepare", "matcher_b")
    g.add_edge(["matcher_a", "matcher_b"], "verify")
    g.add_edge("verify", "keyword_analyzer")
    g.add_edge("keyword_analyzer", "enhancer")
    g.add_edge("enhancer", "report_builder")
    g.add_edge("report_builder", "summary")
    g.add_edge("summary", END)
    return g.compile()


@dataclass
class AnalysisOutcome:
    results: List[MatchResult]
    total_experience: Experience
    keywords: KeywordAnalysis
    kw_evidence: Dict[str, str]
    suggestions: List[BulletSuggestion]
    report: Report
    markdown: str
    warnings: List[str]


def analyze(jd: ParsedJD, cv: ParsedCV, cv_text: str, keys: List[KeyConfig],
            today: Optional[date] = None, use_llm_summary: bool = False) -> AnalysisOutcome:
    init = {"jd": jd, "cv": cv, "cv_text": cv_text}
    if today:
        init["today"] = today
    out = make_graph_b(keys, use_llm_summary).invoke(init)

    errors = []
    if out.get("a_error"):
        errors.append(f"Matching (part 1): {out['a_error']}")
    if out.get("b_error"):
        errors.append(f"Matching (part 2): {out['b_error']}")
    if errors:
        raise AnalyzeFailed(
            "Couldn't finish the analysis. The part that worked is saved, so retrying only repeats the failed part.\n"
            + "\n".join(errors))

    warnings = out.get("warnings", [])
    rep = out["report"]
    return AnalysisOutcome(
        results=out["results"], total_experience=out["total_experience"], keywords=out["kw"],
        kw_evidence=out["kw_evidence"], suggestions=out.get("suggestions", []), report=rep,
        markdown=report_mod.render_markdown(rep, out["kw_evidence"], warnings), warnings=warnings)
