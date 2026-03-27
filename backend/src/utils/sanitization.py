"""
Utilities for sanitizing sensitive data in logs and error messages.
Prevents leaking of passwords, API keys, tokens, and other credentials.
"""

from typing import Any

# Sensitive field names to redact (case-insensitive)
SENSITIVE_FIELDS = {
    "password",
    "passwd",
    "pwd",
    "secret",
    "api_key",
    "apikey",
    "api-key",
    "token",
    "auth",
    "authorization",
    "cst",
    "securitytoken",
    "security_token",
    "security-token",
    "x_security_token",
    "x-security-token",
    "credential",
    "credentials",
}


def sanitize_dict(data: dict[str, Any], redact_value: str = "***REDACTED***") -> dict[str, Any]:
    """
    Sanitize a dictionary by redacting sensitive field values.

    Args:
        data: Dictionary to sanitize
        redact_value: Value to replace sensitive data with

    Returns:
        Sanitized copy of the dictionary
    """
    if not isinstance(data, dict):
        return data

    sanitized = {}

    for key, value in data.items():
        key_lower = key.lower()

        # Check if key matches any sensitive field
        if any(sensitive in key_lower for sensitive in SENSITIVE_FIELDS):
            sanitized[key] = redact_value
        elif isinstance(value, dict):
            sanitized[key] = sanitize_dict(value, redact_value)
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_dict(item, redact_value) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            sanitized[key] = value

    return sanitized


def sanitize_url(url: str) -> str:
    """
    Sanitize a URL by masking password if present.

    Examples:
        postgresql://user:password@host:5432/db -> postgresql://user:***@host:5432/db
        redis://:password@host:6379/0 -> redis://:***@host:6379/0

    Args:
        url: URL to sanitize

    Returns:
        Sanitized URL with masked password
    """
    if not url or "://" not in url:
        return url

    # Split into scheme and rest
    scheme, rest = url.split("://", 1)

    # Check if there's a password (format: user:pass@host or :pass@host)
    if "@" in rest:
        credentials, host_part = rest.rsplit("@", 1)

        if ":" in credentials:
            # Has password
            user_part, _ = credentials.split(":", 1)
            return f"{scheme}://{user_part}:***@{host_part}"

    return url


def sanitize_log_message(message: str) -> str:
    """
    Sanitize a log message by masking potential sensitive data patterns.

    Masks:
    - URLs with passwords (postgresql://..., redis://...)
    - JSON with password fields
    - Token-like strings (long alphanumeric sequences)

    Args:
        message: Log message to sanitize

    Returns:
        Sanitized message
    """
    import re

    # Replace URLs with passwords
    message = re.sub(
        r"(postgresql|redis|mysql|mongodb)://([^:]+):([^@]+)@",
        r"\1://\2:***@",
        message,
    )

    # Replace quoted passwords in key-value pairs
    message = re.sub(
        r'("password"|"passwd"|"pwd"|"secret"|"api_key"|"token")\s*:\s*"[^"]*"',
        r'\1: "***"',
        message,
        flags=re.IGNORECASE,
    )

    return message
