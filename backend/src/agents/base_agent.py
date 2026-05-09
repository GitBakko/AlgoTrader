# MANTIS-EVOLUTION: Agent base class
"""
MantisBaseAgent — abstract base class for all agents in the MANTIS AI
multi-agent trading system.

Phase 14b (2026-05-08): the LLM call site moved from the anthropic
client to the provider-agnostic ``LLMProvider`` interface
(``src/llm_provider``). Production runs against Ollama on GX10 by
default; tests inject a FakeProvider via the constructor.

Each agent subclass:
  - Sets ``role`` (AgentRole) and ``output_schema`` (Pydantic BaseModel
    subclass) as class variables.
  - Implements ``get_system_prompt()`` to supply a role-specific system
    prompt.
  - Implements ``_build_user_message()`` to format a MarketContext into
    a natural-language user message.

The base class handles:
  - Lazy resolution of the ``LLMProvider`` singleton.
  - Building the full system prompt (role prompt + JSON schema hint).
  - Calling ``provider.generate(json_mode=True)`` and parsing the JSON
    response into ``output_schema``.
  - Graceful failure: ``analyze()`` always returns ``None`` instead of
    crashing so a single-agent failure never brings down the whole
    pipeline.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod

from loguru import logger
from pydantic import BaseModel

from src.agents.schemas import AgentRole, MarketContext
from src.llm_provider.base import LLMProvider


class MantisBaseAgent(ABC):
    """
    Abstract base agent. Subclasses define:

    - ``role``: AgentRole enum (class variable)
    - ``output_schema``: Pydantic model class for structured output
    - ``get_system_prompt()``: role-specific system prompt
    - ``_build_user_message()``: format MarketContext into user message
    """

    role: AgentRole
    output_schema: type[BaseModel]

    def __init__(
        self,
        model: str | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.2,
        provider: LLMProvider | None = None,
    ) -> None:
        # ``model`` is accepted for back-compat with callers that still
        # pass an Anthropic identifier (orchestrator, tests). Ollama
        # backend ignores it — model selection is owned by the
        # LLMProvider configuration.
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._provider = provider

    @abstractmethod
    def get_system_prompt(self) -> str:
        """Return the role-specific system prompt for this agent."""
        ...

    @abstractmethod
    def _build_user_message(self, context: MarketContext) -> str:
        """Format a MarketContext into the user-turn message."""
        ...

    async def analyze(self, context: MarketContext) -> BaseModel | None:
        """Run analysis. Returns parsed output_schema or None on any failure."""
        try:
            return await self._call_llm(context)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[{self.role.value}] Agent analysis failed: {exc!r}")
            return None

    async def _call_llm(self, context: MarketContext) -> BaseModel:
        """Call the LLMProvider and parse the JSON response."""
        provider = self._get_provider()
        system_prompt = self.get_system_prompt()
        user_message = self._build_user_message(context)

        schema_hint = json.dumps(self.output_schema.model_json_schema(), indent=2)
        full_system = (
            f"{system_prompt}\n\n"
            f"Respond ONLY with valid JSON matching this schema:\n"
            f"```json\n{schema_hint}\n```"
        )

        text = await provider.generate(
            user_message,
            system=full_system,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            json_mode=True,
        )

        # M6 + M12 fix: share the more robust fence stripper used by the
        # vision analyser. The previous inline strip mishandled
        # space-padded fences (` \`\`\` json `) and could truncate JSON
        # bodies whose content legitimately included triple-backticks.
        from src.vision.vision_analyzer import _strip_fences  # noqa: PLC0415

        text = _strip_fences(text).strip()

        data = json.loads(text)
        return self.output_schema.model_validate(data)

    def _get_provider(self) -> LLMProvider:
        """Return the injected provider or the configured singleton."""
        if self._provider is None:
            from src.llm_provider.factory import get_llm_provider  # noqa: PLC0415

            self._provider = get_llm_provider()
        return self._provider
