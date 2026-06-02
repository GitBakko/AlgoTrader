import pytest
from unittest.mock import AsyncMock
from src.broker.client import CapitalComClient


@pytest.mark.asyncio
async def test_switch_account_puts_session():
    c = CapitalComClient(api_url="https://x", api_key="k", email="e", password="p")
    c._request = AsyncMock(return_value={"accountId": "EXP123"})
    out = await c.switch_account("EXP123")
    c._request.assert_awaited_once_with("PUT", "/api/v1/session", json={"accountId": "EXP123"})
    assert out["accountId"] == "EXP123"


@pytest.mark.asyncio
async def test_get_active_account_id():
    c = CapitalComClient(api_url="https://x", api_key="k", email="e", password="p")
    c._request = AsyncMock(return_value={"accountId": "EXP123", "clientId": "c"})
    assert await c.get_active_account_id() == "EXP123"
