"""
Tests for MantisBaseAgent — the abstract base class for all MANTIS AI agents.

Uses unittest.mock to avoid real Anthropic API calls.
All async tests run automatically via asyncio_mode = auto in pytest.ini.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.schemas import AgentRole, MarketContext, TechnicalReport


# ---------------------------------------------------------------------------
# Concrete mock agent for testing (not abstract)
# ---------------------------------------------------------------------------


def _make_mock_agent(**kwargs):
    """
    Import MantisBaseAgent and return a concrete MockAgent instance.
    Deferred import so that if the module doesn't exist yet, only the
    test that calls this helper fails (not collection-time).
    """
    from src.agents.base_agent import MantisBaseAgent  # noqa: PLC0415

    class MockAgent(MantisBaseAgent):
        role = AgentRole.TECHNICAL
        output_schema = TechnicalReport

        def get_system_prompt(self) -> str:
            return "You are a technical analysis agent."

        def _build_user_message(self, context: MarketContext) -> str:
            return f"Analyse {context.epic} at {context.current_price}"

    return MockAgent(**kwargs)


def _make_valid_technical_report(symbol: str = "GOLD") -> TechnicalReport:
    return TechnicalReport(
        symbol=symbol,
        trend_direction="BULLISH",
        strength_score=0.75,
        key_support_levels=[2300.0],
        key_resistance_levels=[2400.0],
        active_patterns=["golden_cross"],
        timeframe_consensus={"15min": "BULLISH"},
        rationale="EMA aligned, strong momentum.",
    )


def _make_context(epic: str = "GOLD") -> MarketContext:
    return MarketContext(epic=epic, current_price=2350.0, atr=12.5)


# ---------------------------------------------------------------------------
# Test: Initialisation
# ---------------------------------------------------------------------------


class TestInit:
    def test_init_defaults(self):
        """Default constructor should use the canonical MANTIS model settings."""
        agent = _make_mock_agent()
        assert agent.model == "claude-sonnet-4-20250514"
        assert agent.max_tokens == 2000
        assert agent.temperature == 0.2
        assert agent._client is None  # lazy-init — not created until first call

    def test_init_custom_model(self):
        """Custom constructor values should override defaults."""
        agent = _make_mock_agent(
            model="claude-opus-4-5",
            max_tokens=4096,
            temperature=0.0,
        )
        assert agent.model == "claude-opus-4-5"
        assert agent.max_tokens == 4096
        assert agent.temperature == 0.0

    def test_token_budget_default(self):
        """Default max_tokens must be at least 1000 to allow reasonable JSON output."""
        agent = _make_mock_agent()
        assert agent.max_tokens >= 1000

    def test_class_variables_set(self):
        """Concrete subclass must expose role and output_schema class variables."""
        agent = _make_mock_agent()
        assert agent.role == AgentRole.TECHNICAL
        assert agent.output_schema is TechnicalReport


# ---------------------------------------------------------------------------
# Test: analyze() public interface
# ---------------------------------------------------------------------------


class TestAnalyze:
    async def test_analyze_calls_llm_and_parses(self):
        """analyze() should delegate to _call_llm and return its result."""
        agent = _make_mock_agent()
        expected = _make_valid_technical_report()
        context = _make_context()

        with patch.object(agent, "_call_llm", new=AsyncMock(return_value=expected)) as mock_llm:
            result = await agent.analyze(context)

        assert result is expected
        mock_llm.assert_awaited_once_with(context)

    async def test_analyze_returns_none_on_llm_failure(self):
        """analyze() must swallow exceptions from _call_llm and return None."""
        agent = _make_mock_agent()
        context = _make_context()

        with patch.object(agent, "_call_llm", new=AsyncMock(side_effect=RuntimeError("API down"))):
            result = await agent.analyze(context)

        assert result is None

    async def test_analyze_returns_none_on_json_parse_failure(self):
        """analyze() must also swallow JSON/Pydantic validation errors."""
        agent = _make_mock_agent()
        context = _make_context()

        with patch.object(agent, "_call_llm", new=AsyncMock(side_effect=ValueError("bad json"))):
            result = await agent.analyze(context)

        assert result is None

    async def test_analyze_returns_none_on_unexpected_exception(self):
        """Any exception type should be caught — pipeline must never crash."""
        agent = _make_mock_agent()
        context = _make_context()

        with patch.object(agent, "_call_llm", new=AsyncMock(side_effect=KeyError("missing_key"))):
            result = await agent.analyze(context)

        assert result is None


# ---------------------------------------------------------------------------
# Test: _call_llm internal method
# ---------------------------------------------------------------------------


class TestCallLlm:
    def _make_llm_response(self, text: str) -> MagicMock:
        """Build a minimal mock of an Anthropic message response."""
        content_block = MagicMock()
        content_block.text = text
        response = MagicMock()
        response.content = [content_block]
        return response

    async def test_call_llm_parses_clean_json(self):
        """_call_llm should parse a clean JSON response into output_schema."""
        agent = _make_mock_agent()
        report = _make_valid_technical_report("GOLD")
        json_text = report.model_dump_json()

        mock_create = AsyncMock(return_value=self._make_llm_response(json_text))
        mock_client = MagicMock()
        mock_client.messages.create = mock_create
        agent._client = mock_client

        context = _make_context("GOLD")
        result = await agent._call_llm(context)

        assert isinstance(result, TechnicalReport)
        assert result.symbol == "GOLD"
        assert result.trend_direction == "BULLISH"
        mock_create.assert_awaited_once()

    async def test_call_llm_strips_markdown_fences(self):
        """_call_llm must strip ```json ... ``` fences before parsing."""
        agent = _make_mock_agent()
        report = _make_valid_technical_report("GOLD")
        raw_json = report.model_dump_json()
        fenced_text = f"```json\n{raw_json}\n```"

        mock_create = AsyncMock(return_value=self._make_llm_response(fenced_text))
        mock_client = MagicMock()
        mock_client.messages.create = mock_create
        agent._client = mock_client

        context = _make_context("GOLD")
        result = await agent._call_llm(context)

        assert isinstance(result, TechnicalReport)
        assert result.symbol == "GOLD"

    async def test_call_llm_passes_correct_params(self):
        """_call_llm must forward model, max_tokens, temperature, system, messages."""
        agent = _make_mock_agent(model="claude-haiku-3-5", max_tokens=1500, temperature=0.1)
        report = _make_valid_technical_report()
        json_text = report.model_dump_json()

        mock_create = AsyncMock(return_value=self._make_llm_response(json_text))
        mock_client = MagicMock()
        mock_client.messages.create = mock_create
        agent._client = mock_client

        context = _make_context()
        await agent._call_llm(context)

        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["model"] == "claude-haiku-3-5"
        assert call_kwargs["max_tokens"] == 1500
        assert call_kwargs["temperature"] == 0.1
        assert "system" in call_kwargs
        assert "messages" in call_kwargs

    async def test_call_llm_includes_schema_hint_in_system(self):
        """System prompt must include the output_schema JSON schema."""
        agent = _make_mock_agent()
        report = _make_valid_technical_report()

        mock_create = AsyncMock(return_value=self._make_llm_response(report.model_dump_json()))
        mock_client = MagicMock()
        mock_client.messages.create = mock_create
        agent._client = mock_client

        await agent._call_llm(_make_context())

        system_arg = mock_create.call_args.kwargs["system"]
        # Schema hint should be embedded in the system prompt
        assert "json" in system_arg.lower()
        assert "symbol" in system_arg  # TechnicalReport has a 'symbol' field

    async def test_call_llm_user_message_uses_context(self):
        """User message must be built from context by _build_user_message."""
        agent = _make_mock_agent()
        report = _make_valid_technical_report()

        mock_create = AsyncMock(return_value=self._make_llm_response(report.model_dump_json()))
        mock_client = MagicMock()
        mock_client.messages.create = mock_create
        agent._client = mock_client

        context = _make_context("GOLD")
        await agent._call_llm(context)

        messages_arg = mock_create.call_args.kwargs["messages"]
        assert len(messages_arg) == 1
        assert messages_arg[0]["role"] == "user"
        assert "GOLD" in messages_arg[0]["content"]


# ---------------------------------------------------------------------------
# Test: _get_client lazy initialisation
# ---------------------------------------------------------------------------


class TestGetClient:
    def test_get_client_lazy_init(self):
        """_get_client should create the Anthropic client on first call."""
        agent = _make_mock_agent()
        assert agent._client is None

        mock_anthropic_module = MagicMock()
        mock_async_client = MagicMock()
        mock_anthropic_module.AsyncAnthropic.return_value = mock_async_client

        with patch.dict("sys.modules", {"anthropic": mock_anthropic_module}):
            client = agent._get_client()

        assert client is mock_async_client
        mock_anthropic_module.AsyncAnthropic.assert_called_once()

    def test_get_client_reuses_instance(self):
        """_get_client should return the same client on subsequent calls."""
        agent = _make_mock_agent()
        mock_client = MagicMock()
        agent._client = mock_client

        result = agent._get_client()
        assert result is mock_client

    def test_get_client_import_error_propagates(self):
        """If anthropic is not installed, ImportError should propagate clearly."""
        import sys
        agent = _make_mock_agent()

        # Temporarily hide the anthropic module
        original = sys.modules.pop("anthropic", None)
        try:
            with pytest.raises((ImportError, ModuleNotFoundError)):
                agent._get_client()
        finally:
            if original is not None:
                sys.modules["anthropic"] = original


# ---------------------------------------------------------------------------
# Test: Abstract interface enforcement
# ---------------------------------------------------------------------------


class TestAbstractInterface:
    def test_cannot_instantiate_directly(self):
        """MantisBaseAgent must be abstract — direct instantiation must fail."""
        from src.agents.base_agent import MantisBaseAgent  # noqa: PLC0415

        with pytest.raises(TypeError):
            MantisBaseAgent()  # type: ignore[abstract]

    def test_subclass_without_get_system_prompt_fails(self):
        """Subclass missing get_system_prompt() must raise TypeError on instantiation."""
        from src.agents.base_agent import MantisBaseAgent  # noqa: PLC0415

        class IncompleteAgent(MantisBaseAgent):
            role = AgentRole.RISK
            output_schema = TechnicalReport

            def _build_user_message(self, context: MarketContext) -> str:
                return ""

        with pytest.raises(TypeError):
            IncompleteAgent()

    def test_subclass_without_build_user_message_fails(self):
        """Subclass missing _build_user_message() must raise TypeError on instantiation."""
        from src.agents.base_agent import MantisBaseAgent  # noqa: PLC0415

        class IncompleteAgent(MantisBaseAgent):
            role = AgentRole.RISK
            output_schema = TechnicalReport

            def get_system_prompt(self) -> str:
                return ""

        with pytest.raises(TypeError):
            IncompleteAgent()
