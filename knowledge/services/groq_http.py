from __future__ import annotations

import re
import threading
import time

import requests
from django.conf import settings


RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_last_request_at = 0.0
_request_lock = threading.Lock()


def _rate_limit_spacing(response) -> float:
    """Estima espaçamento seguro a partir do próprio erro da Groq."""
    text = response.text or ''
    match = re.search(
        r'Limit\s+([0-9]+).*?Requested\s+([0-9]+)',
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return 0.0

    try:
        limit = float(match.group(1))
        requested = float(match.group(2))
    except (TypeError, ValueError):
        return 0.0

    if limit <= 0 or requested <= 0:
        return 0.0

    # requested / tokens-por-minuto convertido para segundos + margem.
    return min((requested / limit) * 60.0 + 2.0, 60.0)


def _retry_delay(response, attempt: int) -> float:
    retry_after = response.headers.get('Retry-After')
    candidates = []

    if retry_after:
        try:
            candidates.append(float(retry_after) + 2.0)
        except (TypeError, ValueError):
            pass

    match = re.search(
        r'try again in\s+([0-9]+(?:\.[0-9]+)?)s',
        response.text or '',
        flags=re.IGNORECASE,
    )
    if match:
        try:
            candidates.append(float(match.group(1)) + 2.0)
        except ValueError:
            pass

    spacing = _rate_limit_spacing(response)
    if spacing:
        candidates.append(spacing)

    if candidates:
        return max(2.0, min(max(candidates), 60.0))

    return min(3.0 * (2 ** attempt), 45.0)


def _wait_for_min_interval(min_interval: float) -> None:
    global _last_request_at

    if min_interval <= 0:
        return

    with _request_lock:
        elapsed = time.monotonic() - _last_request_at
        remaining = min_interval - elapsed
        if remaining > 0:
            time.sleep(remaining)
        _last_request_at = time.monotonic()


def _is_json_generation_error(response) -> bool:
    if response.status_code != 400:
        return False
    text = (response.text or '').casefold()
    return (
        'json_validate_failed' in text
        or 'failed to generate json' in text
        or 'failed to validate json' in text
    )


def post_groq(
    payload: dict,
    *,
    max_attempts: int = 8,
    min_interval: float = 0.0,
):
    """POST para Groq com pacing e retry de 429/5xx/JSON inválido."""
    response = None

    for attempt in range(max_attempts):
        _wait_for_min_interval(min_interval)

        response = requests.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {settings.GROQ_API_KEY}',
                'Content-Type': 'application/json',
            },
            json=payload,
            timeout=settings.AI_TIMEOUT,
        )

        if response.status_code < 400:
            return response

        retryable = (
            response.status_code in RETRYABLE_STATUS
            or _is_json_generation_error(response)
        )
        if not retryable or attempt >= max_attempts - 1:
            return response

        if _is_json_generation_error(response):
            # Normalmente é uma geração pontualmente inválida do modo JSON.
            time.sleep(min(2.0 + attempt, 8.0))
        else:
            time.sleep(_retry_delay(response, attempt))

    return response
