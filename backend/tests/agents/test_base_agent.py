"""Tests for MantisBaseAgent — Phase 14b provider-based.

Phase 14b (2026-05-08): the base class delegates to ``LLMProvider``
instead of the anthropic client. Tests inject a FakeProvider via the
constructor — no monkey-patching, no anthropic dep.
"""

from __future__ import annotations

import pytest

from src.agents.schemas import AgentRole, MarketContext, TechnicalReport
from src.llm_provider.base import LLMProvider, LLMProviderError


class FakeProvider(LLMProvider):
    """Records the last generate() call and returns scripted output."""

    def __init__(self, response: str | Exception):
        self._response = response
        self.last_prompt: str | None = None
        self.last_system: str | None = None
        self.last_max_tokens: int | None = None
        self.last_temperature: float | None = None
        self.last_json_mode: bool | None = None

    async def generate(self, prompt, *, system=None, max_tokens=1500,
                       temperature=0.0, json_mode=False, keep_alive=None):
        self.last_prompt = prompt
        self.last_system = system
        self.last_max_tokens = max_tokens
        self.last_temperature = temperature
        self.last_json_mode = json_mode
        if isinstance(self._response, Exception):
            raise self._response
        return self._response

    async def analyze_image(self, prompt, image_bytes, *, system=None, max_tokens=1500,
                            temperature=0.0, json_mode=False, keep_alive=None):
        return self._response if not isinstance(self._response, Exception) else ""

    async def embed(self, texts):
        return [[0.0] * self.embedding_dim for _ in texts]

    async def health_check(self):
        return True

    @property
    def embedding_dim(self) -> int:
        return 1024


def _make_mock_agent(provider: LLMProvider | None = None, **kwargs):
    from src.agents.base_agent import MantisBaseAgent  # noqa: PLC0415

    class MockAgent(MantisBaseAgent):
        role = AgentRole.TECHNICAL
        output_schema = TechnicalReport

        def get_system_prompt(self) -> str:
            return "You are a technical analysis agent."

        def _build_user_message(self, context: MarketContext) -> str:
            return f"Analyse {context.epic} at {context.current_price}"

    return MockAgent(provider=provider, **kwargs)


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
# Init
# ---------------------------------------------------------------------------


class TestInit:
    def test_init_defaults(self):
        agent = _make_mock_agent()
        assert agent.model is None
        assert agent.max_tokens == 2000
        assert agent.temperature == 0.2
        assert agent._provider is None  # lazy resolution

    def test_init_custom_values(self):
        fake = FakeProvider("{}")
        agent = _make_mock_agent(provider=fake, model="custom-model",
                                 max_tokens=4096, temperature=0.0)
        assert agent.model == "custom-model"
        assert agent.max_tokens == 4096
        assert agent.temperature == 0.0
        assert agent._provider is fake

    def test_class_variables_set(self):
        agent = _make_mock_agent()
        assert agent.role == AgentRole.TECHNICAL
        assert agent.output_schema is TechnicalReport


# ---------------------------------------------------------------------------
# analyze() — error swallowing
# ---------------------------------------------------------------------------


class TestAnalyze:
    @pytest.mark.asyncio
    async def test_analyze_returns_parsed_report(self):
        report = _make_valid_technical_report()
        fake = FakeProvider(report.model_dump_json())
        agent = _make_mock_agent(provider=fake)

        result = await agent.analyze(_make_context())

        assert isinstance(result, TechnicalReport)
        assert result.symbol == "GOLD"
        assert result.trend_direction == "BULLISH"

    @pytest.mark.asyncio
    async def test_analyze_returns_none_on_provider_error(self):
        fake = FakeProvider(LLMProviderError("network down"))
        agent = _make_mock_agent(provider=fake)

        assert await agent.analyze(_make_context()) is None

    @pytest.mark.asyncio
    async def test_analyze_returns_none_on_invalid_json(self):
        fake = FakeProvider("This is not JSON at all.")
        agent = _make_mock_agent(provider=fake)

        assert await agent.analyze(_make_context()) is None

    @pytest.mark.asyncio
    async def test_analyze_returns_none_on_unexpected_exception(self):
        fake = FakeProvider(KeyError("missing"))
        agent = _make_mock_agent(provider=fake)

        assert await agent.analyze(_make_context()) is None


# ---------------------------------------------------------------------------
# _call_llm internals
# ---------------------------------------------------------------------------


class TestCallLlm:
    @pytest.mark.asyncio
    async def test_strips_markdown_fences(self):
        report = _make_valid_technical_report()
        fenced = f"```json\n{report.model_dump_json()}\n```"
        fake = FakeProvider(fenced)
        agent = _make_mock_agent(provider=fake)

        result = await agent._call_llm(_make_context())

        assert isinstance(result, TechnicalReport)
        assert result.symbol == "GOLD"

    @pytest.mark.asyncio
    async def test_passes_correct_params(self):
        report = _make_valid_technical_report()
        fake = FakeProvider(report.model_dump_json())
        agent = _make_mock_agent(provider=fake, max_tokens=1500, temperature=0.1)

        await agent._call_llm(_make_context())

        assert fake.last_max_tokens == 1500
        assert fake.last_temperature == 0.1
        assert fake.last_json_mode is True

    @pytest.mark.asyncio
    async def test_includes_schema_hint_in_system(self):
        report = _make_valid_technical_report()
        fake = FakeProvider(report.model_dump_json())
        agent = _make_mock_agent(provider=fake)

        await agent._call_llm(_make_context())

        assert fake.last_system is not None
        assert "json" in fake.last_system.lower()
        assert "symbol" in fake.last_system

    @pytest.mark.asyncio
    async def test_user_message_uses_context(self):
        report = _make_valid_technical_report()
        fake = FakeProvider(report.model_dump_json())
        agent = _make_mock_agent(provider=fake)

        await agent._call_llm(_make_context("GOLD"))

        assert fake.last_prompt is not None
        assert "GOLD" in fake.last_prompt


# ---------------------------------------------------------------------------
# Provider lazy resolution
# ---------------------------------------------------------------------------


class TestGetProvider:
    def test_returns_injected_provider(self):
        fake = FakeProvider("{}")
        agent = _make_mock_agent(provider=fake)
        assert agent._get_provider() is fake

    def test_falls_back_to_factory_singleton(self, monkeypatch):
        from src.llm_provider import factory as factory_mod

        sentinel = FakeProvider("{}")
        monkeypatch.setattr(factory_mod, "get_llm_provider", lambda: sentinel)

        agent = _make_mock_agent()  # no injected provider
        assert agent._get_provider() is sentinel
        assert agent._provider is sentinel  # cached after first resolve


# ---------------------------------------------------------------------------
# Abstract enforcement
# ---------------------------------------------------------------------------


class TestAbstractInterface:
    def test_cannot_instantiate_directly(self):
        from src.agents.base_agent import MantisBaseAgent  # noqa: PLC0415

        with pytest.raises(TypeError):
            MantisBaseAgent()  # type: ignore[abstract]

    def test_subclass_without_get_system_prompt_fails(self):
        from src.agents.base_agent import MantisBaseAgent  # noqa: PLC0415

        class IncompleteAgent(MantisBaseAgent):
            role = AgentRole.RISK
            output_schema = TechnicalReport

            def _build_user_message(self, context: MarketContext) -> str:
                return ""

        with pytest.raises(TypeError):
            IncompleteAgent()

    def test_subclass_without_build_user_message_fails(self):
        from src.agents.base_agent import MantisBaseAgent  # noqa: PLC0415

        class IncompleteAgent(MantisBaseAgent):
            role = AgentRole.RISK
            output_schema = TechnicalReport

            def get_system_prompt(self) -> str:
                return ""

        with pytest.raises(TypeError):
            IncompleteAgent()
