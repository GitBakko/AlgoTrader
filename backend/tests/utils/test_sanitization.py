"""Tests for sanitization utilities."""

import pytest

from src.utils.sanitization import sanitize_dict, sanitize_log_message, sanitize_url


class TestSanitizeDict:
    def test_redacts_password_field(self):
        data = {"username": "user", "password": "secret123"}
        result = sanitize_dict(data)
        assert result["username"] == "user"
        assert result["password"] == "***REDACTED***"

    def test_redacts_api_key(self):
        result = sanitize_dict({"api_key": "abc123", "name": "test"})
        assert result["api_key"] == "***REDACTED***"
        assert result["name"] == "test"

    def test_redacts_cst_token(self):
        result = sanitize_dict({"CST": "token_val", "X-SECURITY-TOKEN": "sec"})
        assert result["CST"] == "***REDACTED***"
        assert result["X-SECURITY-TOKEN"] == "***REDACTED***"

    def test_nested_dict(self):
        data = {"config": {"password": "secret", "host": "localhost"}}
        result = sanitize_dict(data)
        assert result["config"]["password"] == "***REDACTED***"
        assert result["config"]["host"] == "localhost"

    def test_list_with_dicts(self):
        data = {"items": [{"token": "abc"}, {"name": "ok"}]}
        result = sanitize_dict(data)
        assert result["items"][0]["token"] == "***REDACTED***"
        assert result["items"][1]["name"] == "ok"

    def test_non_dict_passthrough(self):
        assert sanitize_dict("not a dict") == "not a dict"

    def test_custom_redact_value(self):
        result = sanitize_dict({"password": "x"}, redact_value="[HIDDEN]")
        assert result["password"] == "[HIDDEN]"


class TestSanitizeUrl:
    def test_url_with_password(self):
        url = "postgresql://user:password@host:5432/db"
        assert sanitize_url(url) == "postgresql://user:***@host:5432/db"

    def test_redis_url_with_password(self):
        url = "redis://:mypassword@host:6379/0"
        assert sanitize_url(url) == "redis://:***@host:6379/0"

    def test_url_without_password(self):
        url = "https://example.com/api"
        assert sanitize_url(url) == "https://example.com/api"

    def test_empty_url(self):
        assert sanitize_url("") == ""

    def test_no_scheme(self):
        assert sanitize_url("not-a-url") == "not-a-url"


class TestSanitizeLogMessage:
    def test_masks_postgres_url(self):
        msg = "Connecting to postgresql://admin:secret@host/db"
        result = sanitize_log_message(msg)
        assert "secret" not in result
        assert "***" in result

    def test_masks_password_json(self):
        msg = 'Login: {"password": "mysecret", "user": "admin"}'
        result = sanitize_log_message(msg)
        assert "mysecret" not in result

    def test_clean_message_unchanged(self):
        msg = "Everything is fine"
        assert sanitize_log_message(msg) == msg
