def health_check() -> dict[str, str]:
    """Return a minimal application health payload."""
    return {"status": "ok", "service": "superdeal3"}
