"""ConfiDoc Backend — Review Agent Graph Construction."""

from langgraph.graph import END, StateGraph

from app.services.review.nodes.analyze import analyze_node
from app.services.review.nodes.classify import classify_node
from app.services.review.nodes.extract import extract_node
from app.services.review.nodes.filter import filter_node
from app.services.review.nodes.findings import findings_node
from app.services.review.nodes.synthesize import synthesize_node
from app.services.review.state import ReviewState


def build_review_graph() -> StateGraph:
    graph = StateGraph(ReviewState)

    graph.add_node("classify", classify_node)
    graph.add_node("extract", extract_node)
    graph.add_node("analyze", analyze_node)
    graph.add_node("findings", findings_node)
    graph.add_node("filter", filter_node)
    graph.add_node("synthesize", synthesize_node)

    graph.set_entry_point("classify")
    graph.add_edge("classify", "extract")
    graph.add_edge("extract", "analyze")
    graph.add_edge("analyze", "findings")
    graph.add_edge("findings", "filter")
    graph.add_edge("filter", "synthesize")
    graph.add_edge("synthesize", END)

    return graph


_compiled_graph = None


def get_review_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_review_graph().compile()
    return _compiled_graph


def reset_graph():
    global _compiled_graph
    _compiled_graph = None
