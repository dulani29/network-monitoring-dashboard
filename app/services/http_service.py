'''HTTP health‑check service using requests.'''
import time
from dataclasses import dataclass
from typing import Optional

import requests


@dataclass
class HttpResult:
    url: str
    status_code: Optional[int]
    elapsed_ms: float
    ok: bool  # True if status_code == 200
    error: Optional[str] = None


def check(url: str, timeout: int = 5) -> HttpResult:
    """GET *url* and return timing information.
    Returns ok=True only when the response status is 200.
    """
    start = time.perf_counter()
    try:
        resp = requests.get(url, timeout=timeout)
        elapsed = (time.perf_counter() - start) * 1000.0
        return HttpResult(
            url=url,
            status_code=resp.status_code,
            elapsed_ms=round(elapsed, 2),
            ok=resp.status_code == 200,
        )
    except Exception as exc:
        elapsed = (time.perf_counter() - start) * 1000.0
        return HttpResult(
            url=url,
            status_code=None,
            elapsed_ms=round(elapsed, 2),
            ok=False,
            error=str(exc),
        )
