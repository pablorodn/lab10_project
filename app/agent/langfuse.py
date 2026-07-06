from typing import Any

from app.config import get_settings


def create_langfuse_callback() -> Any | None:
    settings = get_settings()
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return None
    from langfuse import Langfuse
    from langfuse.langchain import CallbackHandler

    Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )
    return CallbackHandler(public_key=settings.langfuse_public_key)


def build_langfuse_tags(*, is_resume: bool) -> list[str]:
    invocation_tag = "resume" if is_resume else "message"
    return ["lab10_project", "interactive", invocation_tag]


def augment_invoke_config(
    config: dict[str, Any],
    *,
    user_id: str,
    session_id: str,
    is_resume: bool,
) -> dict[str, Any]:
    metadata = {
        "langfuse_user_id": user_id,
        "langfuse_session_id": session_id,
        "langfuse_tags": build_langfuse_tags(is_resume=is_resume),
    }
    merged: dict[str, Any] = {
        **config,
        "metadata": {**config.get("metadata", {}), **metadata},
    }
    callback = create_langfuse_callback()
    if callback is not None:
        merged["callbacks"] = [callback]
    return merged
