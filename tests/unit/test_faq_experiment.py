import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FAQ_SCRIPT = ROOT / "evals" / "run_faq_experiment.py"


def _load_faq_module():
    spec = importlib.util.spec_from_file_location("run_faq_experiment", FAQ_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def faq_module():
    return _load_faq_module()


def test_score_case_uses_keyword_hits_in_real_answer(faq_module):
    case = {"expected_keywords": ["sesion"]}
    assert faq_module.score_case("Puedes crear una sesion desde el sidebar", case) == 1.0
    assert faq_module.score_case("Respuesta simulada para: foo", case) == 0.0


def test_score_case_returns_zero_without_keywords(faq_module):
    case = {"expected_keywords": []}
    assert faq_module.score_case("cualquier respuesta", case) == 0.0


@pytest.mark.anyio
async def test_answer_case_invokes_run_agent(faq_module, monkeypatch):
    calls: list[str] = []

    async def _fake_create_session(_db, _user_id, channel="web"):
        class _Session:
            id = "session-eval-1"

        return _Session()

    async def _fake_run_agent(agent_input):
        calls.append(agent_input.message)

        class _Result:
            response = "Para crear una sesion usa el boton Nueva sesion"

        return _Result()

    monkeypatch.setattr(faq_module, "create_session", _fake_create_session)
    monkeypatch.setattr(faq_module, "run_agent", _fake_run_agent)

    answer = await faq_module.answer_case(
        {"question": "como crear una nueva sesion"},
        db=object(),
        user_id="user-1",
        enabled_tools=["list_enabled_tools"],
        system_prompt="prompt",
    )

    assert calls == ["como crear una nueva sesion"]
    assert faq_module.score_case(answer, {"expected_keywords": ["sesion"]}) == 1.0


@pytest.mark.anyio
async def test_run_faq_eval_without_langfuse_uses_real_answers(faq_module, monkeypatch):
    async def _fake_answer_case(case, **kwargs):
        if "hitl" in case["question"]:
            return "Puedes aprobar una accion desde el modal de confirmacion"
        return "no relevante"

    monkeypatch.setattr(faq_module, "is_langfuse_configured", lambda: False)
    monkeypatch.setattr(faq_module, "answer_case", _fake_answer_case)

    cases = [
        {"question": "como aprobar una accion hitl", "expected_keywords": ["aprob"]},
        {"question": "otra cosa", "expected_keywords": ["aprob"]},
    ]
    final_score = await faq_module.run_faq_eval(
        cases,
        db=object(),
        user_id="user-1",
        enabled_tools=[],
    )

    assert final_score == pytest.approx(0.5)


@pytest.mark.anyio
async def test_run_faq_eval_reports_langfuse_dataset_run_when_configured(faq_module, monkeypatch):
    captured: dict[str, object] = {}

    class _FakeResult:
        run_evaluations = [type("E", (), {"name": "avg_keyword_hit_ratio", "value": 0.75})()]
        item_results = []

    class _FakeLangfuse:
        def run_experiment(self, **kwargs):
            captured.update(kwargs)
            return _FakeResult()

    async def _fake_answer_case(case, **kwargs):
        return f"respuesta con {case['expected_keywords'][0]}"

    monkeypatch.setattr(faq_module, "is_langfuse_configured", lambda: True)
    monkeypatch.setattr(faq_module, "answer_case", _fake_answer_case)
    import langfuse as langfuse_module

    monkeypatch.setattr(langfuse_module, "get_client", lambda: _FakeLangfuse())

    cases = [{"question": "q1", "expected_keywords": ["aprob"]}]
    final_score = await faq_module.run_faq_eval(
        cases,
        db=object(),
        user_id="user-1",
        enabled_tools=[],
    )

    assert final_score == pytest.approx(0.75)
    assert captured["name"] == "lab10_project_faq"
    assert captured["data"] == faq_module.cases_to_experiment_data(cases)
