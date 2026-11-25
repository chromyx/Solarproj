"""Runtime settings from environment variables. No secrets are stored in the repository."""

from __future__ import annotations

import os

EXECUTION_MODE = "SIMULATION_ONLY"  # Live order entry does not exist in this codebase.


class SettingsError(RuntimeError):
    pass


def database_url() -> str:
    url = os.environ.get("POWERDESK_DATABASE_URL")
    if not url:
        raise SettingsError(
            "POWERDESK_DATABASE_URL is not set. Example (local dev only): "
            "postgresql+psycopg://powerdesk:powerdesk_dev@localhost:5432/powerdesk"
        )
    return url
