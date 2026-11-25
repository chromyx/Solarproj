"""Shared ingestion pieces: polite HTTP fetching and raw-payload storage."""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.orm import Session

from powerdesk.db.models import RawPayload

log = logging.getLogger(__name__)

USER_AGENT = "powerdesk-market-research/0.1 (internal analysis; low request rate)"
RETRY_STATUS = {429, 500, 502, 503, 504}


class FetchError(RuntimeError):
    pass


@dataclass(frozen=True)
class Fetched:
    url: str
    params: dict[str, Any]
    status: int
    content_type: str | None
    content: bytes
    fetched_at_utc: datetime

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


class PoliteHttp:
    """HTTP client with a minimum delay between requests and retries with exponential backoff."""

    def __init__(
        self,
        min_interval_s: float = 3.0,
        max_attempts: int = 4,
        backoff_base_s: float = 5.0,
        timeout_s: float = 60.0,
        sleep: Callable[[float], None] = time.sleep,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._min_interval_s = min_interval_s
        self._max_attempts = max_attempts
        self._backoff_base_s = backoff_base_s
        self._sleep = sleep
        self._last_request_at: float | None = None
        self._client = httpx.Client(
            timeout=timeout_s,
            headers={"User-Agent": USER_AGENT},
            transport=transport,
            follow_redirects=False,
        )

    def close(self) -> None:
        self._client.close()

    def pause(self, seconds: float) -> None:
        """Extra wait, e.g. after the server returned an error page."""
        self._sleep(seconds)

    def _wait_turn(self) -> None:
        if self._last_request_at is not None:
            wait = self._min_interval_s - (time.monotonic() - self._last_request_at)
            if wait > 0:
                self._sleep(wait)
        self._last_request_at = time.monotonic()

    def request(
        self,
        method: str,
        url: str,
        data: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Fetched:
        last_error: str = ""
        for attempt in range(1, self._max_attempts + 1):
            self._wait_turn()
            try:
                resp = self._client.request(method, url, data=data, headers=headers)
            except httpx.HTTPError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            else:
                if resp.status_code == 200:
                    return Fetched(
                        url=url,
                        params=dict(data or {}),
                        status=resp.status_code,
                        content_type=resp.headers.get("content-type"),
                        content=resp.content,
                        fetched_at_utc=datetime.now(UTC),
                    )
                last_error = f"HTTP {resp.status_code}"
                if resp.status_code not in RETRY_STATUS:
                    break
            if attempt < self._max_attempts:
                delay = self._backoff_base_s * 2 ** (attempt - 1)
                log.warning("fetch failed url=%s attempt=%d error=%s retry_in=%.0fs",
                            url, attempt, last_error, delay)
                self._sleep(delay)
        raise FetchError(f"{method} {url} failed after retries: {last_error}")


def store_raw_payload(
    session: Session,
    source_name: str,
    fetched: Fetched,
    license_status: str,
    note: str | None = None,
    params_for_record: dict[str, Any] | None = None,
) -> RawPayload:
    """Persist the exact bytes received. Raw payloads are append-only (enforced by a DB trigger)."""
    raw = RawPayload(
        source_name=source_name,
        request_url=fetched.url,
        request_params=params_for_record if params_for_record is not None else fetched.params,
        fetched_at_utc=fetched.fetched_at_utc,
        http_status=fetched.status,
        content_type=fetched.content_type,
        content_sha256=fetched.sha256,
        content=fetched.content,
        license_status=license_status,
        note=note,
    )
    session.add(raw)
    session.flush()
    return raw
