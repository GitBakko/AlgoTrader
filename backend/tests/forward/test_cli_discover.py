import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))

import pytest
from unittest.mock import AsyncMock
from src.broker.models import Account


@pytest.mark.asyncio
async def test_discover_account_finds_named_account():
    import forward_lab
    client = AsyncMock()
    client.get_accounts.return_value = [
        Account.model_validate({"accountId": "SOAK1", "accountName": "Primary",
                                "accountType": "DEMO", "currency": "USD"}),
        Account.model_validate({"accountId": "EXP123", "accountName": "Account Demo",
                                "accountType": "DEMO", "currency": "USD"}),
    ]
    acc_id = await forward_lab.discover_account(client, "Account Demo")
    assert acc_id == "EXP123"
