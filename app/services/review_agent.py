"""ConfiDoc — LangGraph Document Review Agent (Facade).

This is a slim facade for backward compatibility.
Logic has been moved to app.services.review.*
"""

from typing import Any

from app.core.logging import get_logger
from app.services.review.constants import STEP_LABELS, STEPS_ORDER
from app.services.review.graph import get_review_graph
from app.services.review.graph import reset_graph as _reset_graph
from app.services.review.llm import (
    ReviewAgentTransientError,
    _raise_for_llm_status,
)
from app.services.review.llm import (
    llm_call as _llm_call,
)
from app.services.review.state import (
    ReviewState,
    fallback_review_state,
    initial_review_state,
    stream_payload,
)

logger = get_logger(__name__)


async def run_review(
    anonymized_text: str,
    entity_summary: dict[str, int] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    graph = get_review_graph()
    initial_st = initial_review_state(anonymized_text, entity_summary, **kwargs)

    try:
        final_state = await graph.ainvoke(initial_st)
        return dict(final_state)
    except ReviewAgentTransientError as exc:
        logger.warning("review_agent_degraded", error=str(exc), code=exc.code)
        return dict(
            fallback_review_state(
                initial_st,
                reason=str(exc),
                code=exc.code,
            )
        )
    except Exception as exc:
        logger.error("review_agent_failed", error=str(exc))
        return {
            **initial_st,
            "error": (
                "L'analyse n'a pas pu aboutir. Relancez l'analyse ou contactez le support "
                "si le probleme persiste."
            ),
            "error_code": "review_agent_error",
            "current_step": "error",
        }


async def run_review_streaming(
    anonymized_text: str,
    entity_summary: dict[str, int] | None = None,
    **kwargs: Any,
):
    """Yield step updates as they complete (SSE-friendly)."""
    graph = get_review_graph()
    initial_st = initial_review_state(anonymized_text, entity_summary, **kwargs)
    latest_state: ReviewState = dict(initial_st)
    completed_steps: set[str] = set()

    def _iter_chunks(raw: object) -> dict[str, Any]:
        if isinstance(raw, tuple) and len(raw) >= 2:
            mode, payload = raw[0], raw[1]
            if mode == "updates" and isinstance(payload, dict):
                return payload
            if isinstance(payload, dict):
                return payload
            return {}
        if isinstance(raw, dict):
            if raw.get("type") == "updates" and isinstance(raw.get("data"), dict):
                return dict(raw["data"])
            return raw
        return {}

    try:
        async for raw_chunk in graph.astream(
            initial_st,
            stream_mode="updates",
            version="v1",
        ):
            state = _iter_chunks(raw_chunk)
            for node_name, node_output in state.items():
                if node_name not in STEPS_ORDER:
                    continue
                if not isinstance(node_output, dict):
                    continue
                latest_state.update(node_output)
                completed_steps.add(node_name)
                yield {
                    "step": node_name,
                    "label": STEP_LABELS.get(node_name, node_name),
                    "status": "done",
                    "data": {k: v for k, v in node_output.items() if k not in ("anonymized_text",)},
                }

                idx = STEPS_ORDER.index(node_name)
                if idx + 1 < len(STEPS_ORDER):
                    next_step = STEPS_ORDER[idx + 1]
                    yield {
                        "step": next_step,
                        "label": STEP_LABELS.get(next_step, next_step),
                        "status": "running",
                        "data": {},
                    }

        yield {"step": "complete", "label": "Analyse terminee", "status": "complete", "data": {}}

    except ReviewAgentTransientError as exc:
        logger.warning("review_agent_stream_degraded", error=str(exc), code=exc.code)
        fallback = fallback_review_state(latest_state, reason=str(exc), code=exc.code)
        for step in STEPS_ORDER:
            if step in completed_steps:
                continue
            yield {
                "step": step,
                "label": STEP_LABELS.get(step, step),
                "status": "running",
                "data": {},
            }
            yield {
                "step": step,
                "label": STEP_LABELS.get(step, step),
                "status": "done",
                "data": stream_payload(fallback),
            }
        yield {
            "step": "complete",
            "label": "Analyse terminee en mode degrade",
            "status": "complete",
            "data": {"degraded": True, "error_code": exc.code},
        }

    except Exception as exc:
        logger.error("review_agent_stream_failed", error=str(exc))
        yield {
            "step": "error",
            "label": "Erreur",
            "status": "error",
            "data": {
                "error": (
                    "L'analyse n'a pas pu aboutir. Relancez l'analyse ou contactez le "
                    "support si le probleme persiste."
                ),
                "code": "review_agent_error",
            },
        }
