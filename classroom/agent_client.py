"""Call the agent's day specialists. A missing base URL or a down agent is None."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

logger = logging.getLogger("classroom.agent")

_TIMEOUT_S = 2.0


def call_specialist(
    name: str,
    body: Dict[str, Any],
    base_url: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    base = base_url if base_url is not None else os.getenv("AGENT_API_BASE_URL", "")
    base = base.strip().rstrip("/")
    if not base:
        return None
    url = f"{base}/api/v1/classroom/{name}"
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_S) as response:
            parsed = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        logger.warning("classroom specialist %s failed: %s", name, exc)
        return None
    except Exception:
        logger.exception("classroom specialist %s failed", name)
        return None
    return parsed if isinstance(parsed, dict) else None
