from __future__ import annotations

import re
import time

import requests
from django.conf import settings


RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _retry_delay(response, attempt: int) -> float:
    retry_after = response.headers.get('Retry-After')
    if retry_after:
        try:
            return max(2.0, min(float(retry_after) + 1.0, 60.0))
        except (TypeError, ValueError):
            pass

    # A Groq costuma informar no corpo: "Please try again in 14.4975s".
    match = re.search(
        r'try again in\s+([0-9]+(?:\.[0-9]+)?)s',
        response.text or '',
        flags=re.IGNORECASE,
    )
    if match:
        try:
            return max(2.0, min(float(match.group(1)) + 1.0, 60.0))
        except ValueError:
            pass

    # Fallback para indisponibilidade temporária sem indicação explícita.
    return min(3.0 * (2 ** attempt), 45.0)


def post_groq(payload: dict, *, max_attempts: int = 6):
    """POST para chat/completions com retry de 429/5xx e respeito ao Retry-After."""
    response = None

    for attempt in range(max_attempts):
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

        if (
            response.status_code not in RETRYABLE_STATUS
            or attempt >= max_attempts - 1
        ):
            return response

        time.sleep(_retry_delay(response, attempt))

    return response
