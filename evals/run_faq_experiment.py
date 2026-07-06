"""FAQ evaluation experiment against the real agent runtime."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from app.agent.graph import AgentInput, run_agent, warmup_agent_runtime
from app.config import get_settings
from app.db.client import create_server_client
from app.db.queries.sessions import create_session
from app.db.queries.tools import list_enabled_tool_ids

CASES_PATH = Path(__file__).parent / "faq_cases.json"
DEFAULT_SYSTEM_PROMPT = (
    "Eres un asistente útil que responde preguntas sobre el producto lab10_project."
)


def load_cases(path: Path = CASES_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def score_case(answer: str, case: dict[str, Any]) -> float:
    """Lightweight deterministic baseline score for CI (keyword hit ratio)."""
    expected_keywords = case.get("expected_keywords", [])
    if not answer.strip() or not expected_keywords:
        return 0.0
    answer_lower = answer.lower()
    hits = sum(1 for keyword in expected_keywords if keyword.lower() in answer_lower)
    return hits / len(expected_keywords)


def cases_to_experiment_data(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "input": case["question"],
            "expected_output": case.get("expected_keywords", []),
            "metadata": {"question": case["question"]},
        }
        for case in cases
    ]


def is_langfuse_configured() -> bool:
    settings = get_settings()
    return bool(settings.langfuse_public_key and settings.langfuse_secret_key)


async def answer_case(
    case: dict[str, Any],
    *,
    db: Any,
    user_id: str,
    enabled_tools: list[str],
    system_prompt: str,
) -> str:
    session = await create_session(db, user_id, channel="web")
    result = await run_agent(
        AgentInput(
            user_id=user_id,
            session_id=session.id,
            system_prompt=system_prompt,
            db=db,
            enabled_tools=enabled_tools,
            message=case["question"],
        )
    )
    return result.response


async def run_faq_eval(
    cases: list[dict[str, Any]],
    *,
    db: Any,
    user_id: str,
    enabled_tools: list[str],
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    use_langfuse: bool = True,
) -> float:
    if not cases:
        return 0.0
    if use_langfuse and is_langfuse_configured():
        return await _run_with_langfuse(
            cases,
            db=db,
            user_id=user_id,
            enabled_tools=enabled_tools,
            system_prompt=system_prompt,
        )

    scores: list[float] = []
    for case in cases:
        answer = await answer_case(
            case,
            db=db,
            user_id=user_id,
            enabled_tools=enabled_tools,
            system_prompt=system_prompt,
        )
        scores.append(score_case(answer, case))
    return sum(scores) / len(scores)


async def _run_with_langfuse(
    cases: list[dict[str, Any]],
    *,
    db: Any,
    user_id: str,
    enabled_tools: list[str],
    system_prompt: str,
) -> float:
    from langfuse import Evaluation, get_client

    langfuse = get_client()
    experiment_data = cases_to_experiment_data(cases)

    async def faq_task(*, item: dict[str, Any], **_: Any) -> str:
        case = {
            "question": item["input"],
            "expected_keywords": item.get("expected_output", []),
        }
        return await answer_case(
            case,
            db=db,
            user_id=user_id,
            enabled_tools=enabled_tools,
            system_prompt=system_prompt,
        )

    def keyword_evaluator(*, output: Any, expected_output: Any | None = None, **_: Any) -> Evaluation:
        case = {"expected_keywords": expected_output or []}
        score = score_case(str(output), case)
        return Evaluation(
            name="keyword_hit_ratio",
            value=score,
            comment="Deterministic keyword hit ratio from evals/faq_cases.json",
        )

    def average_keyword_evaluator(*, item_results: list[Any], **_: Any) -> Evaluation:
        scores = [
            float(evaluation.value)
            for item_result in item_results
            for evaluation in item_result.evaluations
            if evaluation.name == "keyword_hit_ratio"
        ]
        average = sum(scores) / len(scores) if scores else 0.0
        return Evaluation(
            name="avg_keyword_hit_ratio",
            value=average,
            comment=f"Average over {len(scores)} FAQ cases",
        )

    result = langfuse.run_experiment(
        name="lab10_project_faq",
        description="FAQ evaluation against real run_agent() runtime",
        data=experiment_data,
        task=faq_task,
        evaluators=[keyword_evaluator],
        run_evaluators=[average_keyword_evaluator],
        metadata={"source": "evals/faq_cases.json"},
    )

    for evaluation in result.run_evaluations:
        if evaluation.name == "avg_keyword_hit_ratio":
            return float(evaluation.value)

    item_scores = [
        float(evaluation.value)
        for item_result in result.item_results
        for evaluation in item_result.evaluations
        if evaluation.name == "keyword_hit_ratio"
    ]
    return sum(item_scores) / len(item_scores) if item_scores else 0.0


async def main() -> None:
    print("Running FAQ experiment...")
    cases = load_cases()
    if not cases:
        print("No cases found at evals/faq_cases.json")
        print("score=0.0")
        return

    user_id = os.getenv("EVAL_USER_ID", "").strip()
    if not user_id:
        print("Missing EVAL_USER_ID env var (UUID of an existing profiles.id for eval runs).")
        print("score=0.0")
        sys.exit(1)

    await warmup_agent_runtime()
    db = await create_server_client()
    enabled_tools = await list_enabled_tool_ids(db, user_id)
    final_score = await run_faq_eval(
        cases,
        db=db,
        user_id=user_id,
        enabled_tools=enabled_tools,
    )
    print(f"cases={len(cases)}")
    print(f"score={final_score:.3f}")


if __name__ == "__main__":
    asyncio.run(main())
