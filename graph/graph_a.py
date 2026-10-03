from dataclasses import dataclass, field
from typing import List, TypedDict

from langgraph.graph import StateGraph, START, END

from graph.schemas import ParsedJD, ParsedCV
from graph import parsers
from llm.router import LLMError, KeyConfig


class ParseFailed(Exception):
    """Message is safe to show to the user."""


class ParseState(TypedDict, total=False):
    jd_text: str
    cv_text: str
    parsed_jd: ParsedJD
    parsed_cv: ParsedCV
    jd_warnings: List[str]
    cv_warnings: List[str]
    jd_cached: bool
    cv_cached: bool
    jd_error: str
    cv_error: str


def make_graph_a(keys: List[KeyConfig]):
    """Keys live in the closure, never in graph state."""

    def jd_node(state: ParseState):
        try:
            jd, warns, cached = parsers.parse_jd(state["jd_text"], keys)
            return {"parsed_jd": jd, "jd_warnings": warns, "jd_cached": cached}
        except LLMError as e:
            return {"jd_error": str(e)}

    def cv_node(state: ParseState):
        try:
            cv, warns, cached = parsers.parse_cv(state["cv_text"], keys)
            return {"parsed_cv": cv, "cv_warnings": warns, "cv_cached": cached}
        except LLMError as e:
            return {"cv_error": str(e)}

    g = StateGraph(ParseState)
    g.add_node("jd_parser", jd_node)
    g.add_node("cv_parser", cv_node)
    g.add_edge(START, "jd_parser")       # both start together = parallel
    g.add_edge(START, "cv_parser")
    g.add_edge("jd_parser", END)
    g.add_edge("cv_parser", END)
    return g.compile()


@dataclass
class ParseOutcome:
    jd: ParsedJD
    cv: ParsedCV
    warnings: List[str] = field(default_factory=list)
    jd_cached: bool = False
    cv_cached: bool = False


def parse_documents(jd_text: str, cv_text: str, keys: List[KeyConfig]) -> ParseOutcome:
    out = make_graph_a(keys).invoke({"jd_text": jd_text, "cv_text": cv_text})

    errors = []
    if "jd_error" in out:
        errors.append(f"Job description: {out['jd_error']}")
    if "cv_error" in out:
        errors.append(f"CV: {out['cv_error']}")
    if errors:
        raise ParseFailed(
            "Couldn't finish parsing. The part that worked is saved, so retrying only repeats the failed part.\n"
            + "\n".join(errors))

    return ParseOutcome(
        jd=out["parsed_jd"], cv=out["parsed_cv"],
        warnings=out.get("jd_warnings", []) + out.get("cv_warnings", []),
        jd_cached=out.get("jd_cached", False), cv_cached=out.get("cv_cached", False),
    )
