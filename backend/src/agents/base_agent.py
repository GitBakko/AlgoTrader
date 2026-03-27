# MANTIS-EVOLUTION: Agent base class
"""
MantisBaseAgent — abstract base class for all agents in the MANTIS AI
multi-agent trading system.

Each agent subclass:
  - Sets ``role`` (AgentRole) and ``output_schema`` (Pydantic BaseModel subclass)
    as class variables.
  - Implements ``get_system_prompt()`` to supply a role-specific system prompt.
  - Implements ``_build_user_message()`` to format a MarketContext into a
    natural-language user message.

The base class handles:
  - Lazy-initialisation of the Anthropic AsyncAnthropic client.
  - Building the full system prompt (role prompt + JSON schema hint).
  - Calling the Claude API and parsing the JSON response into ``output_schema``.
  - Graceful failure: ``analyze()`` always returns None instead of crashing so
    that a single-agent failure never brings down the whole pipeline.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod

from loguru import logger
from pydantic import BaseModel

from src.agents.schemas import AgentRole, MarketContext


class MantisBaseAgent(ABC):
    """
    Abstract base agent.  Subclasses define:

    - ``role``: AgentRole enum (class variable)
    - ``output_schema``: Pydantic model class for structured output (class variable)
    - ``get_system_prompt()``: role-specific system prompt
    - ``_build_user_message()``: format MarketContext into user message
    """

    # Subclasses must override these as class variables
    role: AgentRole
    output_schema: type[BaseModel]

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 2000,
        temperature: float = 0.2,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._client = None  # lazy-init anthropic.AsyncAnthropic client

    # ------------------------------------------------------------------
    # Abstract interface — subclasses must implement
    # ------------------------------------------------------------------

    @abstractmethod
    def get_system_prompt(self) -> str:
        """Return the role-specific system prompt for this agent."""
        ...

    @abstractmethod
    def _build_user_message(self, context: MarketContext) -> str:
        """
        Format a MarketContext into the user-turn message that Claude will
        analyse.  Subclasses control the exact structure and level of detail.
        """
        ...

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def analyze(self, context: MarketContext) -> BaseModel | None:
        """
        Run analysis on the given context.

        Returns the parsed ``output_schema`` instance on success, or ``None``
        on any failure.  This method NEVER raises — a single-agent failure
        must not crash the broader pipeline.
        """
        try:
            return await self._call_llm(context)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[{self.role.value}] Agent analysis failed: {exc!r}")
            return None

    # ------------------------------------------------------------------
    # LLM interaction
    # ------------------------------------------------------------------

    async def _call_llm(self, context: MarketContext) -> BaseModel:
        """
        Call the Claude API, parse the JSON response and return a validated
        ``output_schema`` instance.

        Raises on any network, JSON-parse, or Pydantic validation error — the
        caller (``analyze``) catches and converts to None.
        """
        client = self._get_client()
        system_prompt = self.get_system_prompt()
        user_message = self._build_user_message(context)

        # Embed the JSON schema as a hint so the model knows the exact format
        schema_hint = json.dumps(self.output_schema.model_json_schema(), indent=2)
        full_system = (
            f"{system_prompt}\n\n"
            f"Respond ONLY with valid JSON matching this schema:\n"
            f"```json\n{schema_hint}\n```"
        )

        response = await client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=full_system,
            messages=[{"role": "user", "content": user_message}],
        )

        text: str = response.content[0].text

        # Strip markdown code fences that the model sometimes wraps output in
        if text.startswith("```"):
            # Remove opening fence (```json\n or ```\n)
            text = text.split("\n", 1)[1]
            # Remove closing fence
            text = text.rsplit("```", 1)[0]

        data = json.loads(text)
        return self.output_schema.model_validate(data)

    # ------------------------------------------------------------------
    # Client management
    # ------------------------------------------------------------------

    def _get_client(self):
        """
        Lazy-initialise and return the Anthropic AsyncAnthropic client.

        Raises ImportError if the ``anthropic`` package is not installed —
        this surfaces as a clear error rather than a cryptic AttributeError.
        """
        if self._client is None:
            import anthropic  # noqa: PLC0415 — intentional lazy import

            self._client = anthropic.AsyncAnthropic()
        return self._client
