from dataclasses import dataclass
from datetime import date
from typing import List, Optional, TypedDict

from langgraph.graph import StateGraph, START, END

from graph.schemas import ParsedJD, ParsedCV, JDRequirement, MatchResult
from graph import matcher, verify
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


def make_graph_b(keys: List[KeyConfig]):
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

    g = StateGraph(AnalyzeState)
    g.add_node("prepare", prepare)
    g.add_node("matcher_a", make_matcher_node("matcher_a", "group_a", "matches_a", "a_error"))
    g.add_node("matcher_b", make_matcher_node("matcher_b", "group_b", "matches_b", "b_error"))
    g.add_node("verify", verify_node)
    g.add_edge(START, "prepare")
    g.add_edge("prepare", "matcher_a")                      # both matchers run in parallel
    g.add_edge("prepare", "matcher_b")
    g.add_edge(["matcher_a", "matcher_b"], "verify")        # verify waits for both
    g.add_edge("verify", END)
    return g.compile()


@dataclass
class AnalysisOutcome:
    results: List[MatchResult]
    total_experience: Experience


def analyze(jd: ParsedJD, cv: ParsedCV, cv_text: str, keys: List[KeyConfig],
            today: Optional[date] = None) -> AnalysisOutcome:
    init = {"jd": jd, "cv": cv, "cv_text": cv_text}
    if today:
        init["today"] = today
    out = make_graph_b(keys).invoke(init)

    errors = []
    if out.get("a_error"):
        errors.append(f"Matching (part 1): {out['a_error']}")
    if out.get("b_error"):
        errors.append(f"Matching (part 2): {out['b_error']}")
    if errors:
        raise ParseFailedLike(errors)
    return AnalysisOutcome(results=out["results"], total_experience=out["total_experience"])


def ParseFailedLike(errors):
    return AnalyzeFailed(
        "Couldn't finish the analysis. The part that worked is saved, so retrying only repeats the failed part.\n"
        + "\n".join(errors))
