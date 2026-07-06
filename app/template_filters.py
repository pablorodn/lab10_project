from datetime import datetime

from fastapi.templating import Jinja2Templates


def format_session_date(date_str: str | None) -> str:
    if not date_str:
        return ""
    parsed = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    months = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
    return f"{parsed.day} {months[parsed.month - 1]}, {parsed.strftime('%H:%M')}"


def register_template_filters(templates: Jinja2Templates) -> None:
    templates.env.filters["format_session_date"] = format_session_date
