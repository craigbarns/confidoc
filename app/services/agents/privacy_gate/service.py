"""Facade for the DPO Privacy Gate agent."""

from typing import Any

from app.services.agents.privacy_gate.graph import get_privacy_gate_graph
from app.services.agents.privacy_gate.state import initial_privacy_gate_state


async def run_privacy_gate(**kwargs: Any) -> dict[str, Any]:
    graph = get_privacy_gate_graph()
    initial_state = initial_privacy_gate_state(**kwargs)
    final_state = await graph.ainvoke(initial_state)
    return {
        "agent": "privacy_gate",
        "document_id": final_state.get("document_id"),
        "requested_action": final_state.get("normalized_action"),
        "decision": final_state.get("decision"),
        "risk_score": final_state.get("risk_score"),
        "risk_level": final_state.get("risk_level"),
        "reasons": final_state.get("reasons") or [],
        "required_actions": final_state.get("required_actions") or [],
        "allowed_controls": final_state.get("allowed_controls") or [],
        "warnings": final_state.get("warnings") or [],
        "evidence": final_state.get("evidence") or {},
        "steps_completed": final_state.get("steps_completed") or [],
    }

