"""Central logging redaction for credentials and credential-shaped URLs."""

from __future__ import annotations

import logging
import os
import re
import traceback
from urllib.parse import quote, quote_plus

REDACTED = "<redacted>"

SECRET_ENV_NAMES = (
    "ALPHA_VANTAGE_KEY", "ALPHA_VANTAGE_API_KEY", "NEWSAPI_KEY", "NEWS_API_KEY",
    "FRED_API_KEY", "GROQ_API_KEY", "FINNHUB_API_KEY", "FMP_API_KEY",
    "MASSIVE_API_KEY", "TWELVEDATA_API_KEY", "TWELVE_DATA_API_KEY",
    "MARKETSTACK_API_KEY", "SUPABASE_SERVICE_ROLE_KEY", "CLERK_SECRET_KEY",
    "POLYGON_API_KEY", "TIINGO_API_KEY", "GNEWS_API_KEY", "TAVILY_API_KEY",
    "EXA_API_KEY", "BRAVE_API_KEY", "APIFY_API_TOKEN", "GEMINI_API_KEY",
    "LOGO_DEV_SECRET_KEY",
)

_QUERY_SECRET = re.compile(
    r"(?i)([?&\s](?:apikey|api_key|token|access_token|key|secret)=)[^&\s]+"
)


def secret_values() -> tuple[str, ...]:
    values: set[str] = set()
    for name in SECRET_ENV_NAMES:
        value = os.getenv(name, "")
        # Very short values create destructive false positives in normal text.
        if len(value) >= 4:
            values.update((value, quote(value, safe=""), quote_plus(value)))
    return tuple(sorted(values, key=len, reverse=True))


def redact(value: object) -> str:
    text = str(value)
    for secret in secret_values():
        text = text.replace(secret, REDACTED)
    return _QUERY_SECRET.sub(lambda match: f"{match.group(1)}{REDACTED}", text)


class SecretRedactionFilter(logging.Filter):
    """Sanitize the message and any preformatted exception before handlers."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = ()
        if record.exc_info:
            record.exc_text = redact("".join(traceback.format_exception(*record.exc_info)))
        return True


def install() -> None:
    root = logging.getLogger()
    for handler in root.handlers:
        if not any(isinstance(item, SecretRedactionFilter) for item in handler.filters):
            handler.addFilter(SecretRedactionFilter())
