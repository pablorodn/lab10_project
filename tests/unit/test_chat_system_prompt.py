from app.routers.chat import (
    PROFILE_CONTEXT_END,
    PROFILE_CONTEXT_START,
    SYSTEM_PROMPT_GUARDRAILS,
    _build_user_system_prompt,
)


def test_build_user_system_prompt_wraps_profile_block_with_trust_delimiter():
    result = _build_user_system_prompt(
        "Eres un asistente útil.",
        user_name="Pablo",
        language="es",
        timezone="America/Bogota",
    )

    assert PROFILE_CONTEXT_START in result
    assert PROFILE_CONTEXT_END in result
    start_idx = result.index(PROFILE_CONTEXT_START)
    header_idx = result.index("[CONTEXTO DE PERFIL]")
    content_idx = result.index("Nombre del usuario autenticado: Pablo.")
    end_idx = result.index(PROFILE_CONTEXT_END)
    assert start_idx < header_idx < content_idx < end_idx


def test_build_user_system_prompt_includes_guardrails_with_profile_context():
    result = _build_user_system_prompt(
        "Eres un asistente útil.",
        user_name="Pablo",
        language=None,
        timezone=None,
    )

    assert SYSTEM_PROMPT_GUARDRAILS in result


def test_build_user_system_prompt_includes_guardrails_without_profile_context():
    result = _build_user_system_prompt(
        "Eres un asistente útil.",
        user_name=None,
        language=None,
        timezone=None,
    )

    assert PROFILE_CONTEXT_START not in result
    assert SYSTEM_PROMPT_GUARDRAILS in result
