from pathlib import Path

from app.config import get_settings


def _resolve_safe_path(path: str) -> Path:
    settings = get_settings()
    if not settings.is_file_tools_enabled:
        raise PermissionError("FILE_TOOLS_ENABLED is not true")
    candidate = (settings.file_tools_allowed_root / path).resolve()
    if settings.file_tools_allowed_root not in candidate.parents and candidate != settings.file_tools_allowed_root:
        raise PermissionError("Path is outside FILE_TOOLS_ROOT")
    return candidate


def execute_read_file(path: str, offset: int | None = None, limit: int | None = None) -> str:
    target = _resolve_safe_path(path)
    content = target.read_text(encoding="utf-8")
    lines = content.splitlines()
    if offset is None:
        return content
    start = max(offset, 0)
    end = start + (limit if limit is not None else len(lines))
    return "\n".join(lines[start:end])


def execute_write_file(path: str, content: str) -> str:
    target = _resolve_safe_path(path)
    if target.exists():
        raise FileExistsError("Target already exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return "ok"


def execute_edit_file(path: str, old_string: str, new_string: str) -> str:
    target = _resolve_safe_path(path)
    source = target.read_text(encoding="utf-8")
    count = source.count(old_string)
    if count != 1:
        raise ValueError("old_string must match exactly one occurrence")
    target.write_text(source.replace(old_string, new_string), encoding="utf-8")
    return "ok"
