"""LangGraph wiring for the DPO Privacy Gate agent."""

from langgraph.graph import END, StateGraph

from app.services.agents.privacy_gate.nodes import (
    decide_node,
    evaluate_node,
    explain_node,
    normalize_node,
)
from app.services.agents.privacy_gate.state import PrivacyGateState


def build_privacy_gate_graph() -> StateGraph:
    graph = StateGraph(PrivacyGateState)
    graph.add_node("normalize", normalize_node)
    graph.add_node("evaluate", evaluate_node)
    graph.add_node("decide", decide_node)
    graph.add_node("explain", explain_node)

    graph.set_entry_point("normalize")
    graph.add_edge("normalize", "evaluate")
    graph.add_edge("evaluate", "decide")
    graph.add_edge("decide", "explain")
    graph.add_edge("explain", END)
    return graph


_compiled_graph = None


def get_privacy_gate_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_privacy_gate_graph().compile()
    return _compiled_graph


def reset_graph() -> None:
    global _compiled_graph
    _compiled_graph = None
