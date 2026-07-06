from typing import Any

ONBOARDING_KEY = "onboarding_data"


def get_onboarding_data(session: dict[str, Any]) -> dict[str, Any]:
    return session.get(
        ONBOARDING_KEY,
        {
            "name": "",
            "timezone": "America/Bogota",
            "language": "es",
            "agent_name": "Agente",
            "agent_system_prompt": "",
            "enabled_tools": [],
        },
    )


def update_onboarding_data(session: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    current = get_onboarding_data(session)
    current.update(payload)
    session[ONBOARDING_KEY] = current
    return current
