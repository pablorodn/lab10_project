SENSITIVE_KEYWORDS = ("token", "password", "secret", "api key", "credential")


def can_store_memory(content: str) -> bool:
    lowered = content.lower()
    return not any(keyword in lowered for keyword in SENSITIVE_KEYWORDS)
