# MANTIS-EVOLUTION: RAG Context Builder
"""Builds enriched context for LLM agents from news, macro, and memory data."""

from __future__ import annotations

from src.memory_layer.schemas import MemoryContext
from src.rag.schemas import NewsItem, RAGContext


class MantisRAGContextBuilder:
    """
    Builds RAG context string from multiple sources.
    Respects MAX_CONTEXT_TOKENS to keep prompts efficient.
    """

    MAX_CONTEXT_TOKENS: int = 2000  # ~2000 tokens ≈ ~8000 chars

    def __init__(self, max_tokens: int | None = None):
        if max_tokens is not None:
            self.MAX_CONTEXT_TOKENS = max_tokens

    def build(
        self,
        news: list[NewsItem] | None = None,
        sil_data: dict | None = None,
        memory_context: MemoryContext | None = None,
    ) -> RAGContext:
        """
        Build complete RAG context from available sources.
        Truncates to MAX_CONTEXT_TOKENS.
        """
        sections = []
        sources_count = 0

        # 1. News section
        news_section = ""
        if news:
            news_section = self._format_news_section(news[:5])  # top 5 by relevance
            sections.append(news_section)
            sources_count += len(news[:5])

        # 2. Macro/SIL section
        macro_section = ""
        if sil_data:
            macro_section = self._format_macro_section(sil_data)
            sections.append(macro_section)
            sources_count += 1

        # 3. Memory section
        memory_section = ""
        if memory_context:
            memory_section = self._format_memory_section(memory_context)
            sections.append(memory_section)
            sources_count += 1

        # Estimate tokens (rough: 1 token ≈ 4 chars)
        total_chars = sum(len(s) for s in sections)
        estimated_tokens = total_chars // 4

        # Truncate if over budget
        if estimated_tokens > self.MAX_CONTEXT_TOKENS:
            sections = self._truncate_sections(sections, self.MAX_CONTEXT_TOKENS)
            total_chars = sum(len(s) for s in sections)
            estimated_tokens = total_chars // 4

            # Recalculate which section is which after truncation
            news_section, macro_section, memory_section = self._reassign_sections(
                sections,
                news_section,
                macro_section,
                memory_section,
            )

        return RAGContext(
            news_section=news_section,
            macro_section=macro_section,
            memory_section=memory_section,
            total_tokens_estimate=estimated_tokens,
            sources_count=sources_count,
        )

    def _reassign_sections(
        self,
        truncated: list[str],
        orig_news: str,
        orig_macro: str,
        orig_memory: str,
    ) -> tuple[str, str, str]:
        """Map truncated sections back to named fields."""
        # Build a mapping from original section → truncated text
        originals = [s for s in [orig_news, orig_macro, orig_memory] if s]
        reassigned: dict[str, str] = {}
        for i, orig in enumerate(originals):
            reassigned[orig] = truncated[i] if i < len(truncated) else ""

        news = reassigned.get(orig_news, "") if orig_news else ""
        macro = reassigned.get(orig_macro, "") if orig_macro else ""
        memory = reassigned.get(orig_memory, "") if orig_memory else ""
        return news, macro, memory

    def _format_news_section(self, news: list[NewsItem]) -> str:
        """Format news items as concise bullet points."""
        if not news:
            return ""
        lines = ["## Recent News"]
        for item in news:
            sentiment_tag = "+" if item.sentiment > 0.1 else ("-" if item.sentiment < -0.1 else "~")
            line = f"- [{sentiment_tag}] {item.title}"
            if item.lead_paragraph:
                line += f": {item.lead_paragraph[:150]}"
            if item.source:
                line += f" ({item.source})"
            lines.append(line)
        return "\n".join(lines)

    def _format_macro_section(self, sil_data: dict) -> str:
        """Format SIL macro data into readable summary."""
        if not sil_data:
            return ""
        lines = ["## Macro Context"]

        # Fear & Greed
        fg = sil_data.get("sil_fear_greed_value")
        if fg is not None:
            if fg < 0.25:
                label = "Extreme Fear"
            elif fg < 0.45:
                label = "Fear"
            elif fg < 0.55:
                label = "Neutral"
            elif fg < 0.75:
                label = "Greed"
            else:
                label = "Extreme Greed"
            lines.append(f"- Fear & Greed: {fg:.0%} ({label})")

        # Real yield
        ry = sil_data.get("sil_real_yield_10y")
        if ry is not None:
            lines.append(f"- Real Yield 10Y: {ry:.2f}%")

        # COT
        cot = sil_data.get("sil_cot_net_position_norm")
        if cot is not None:
            if cot > 0.2:
                bias = "institutional long"
            elif cot < -0.2:
                bias = "institutional short"
            else:
                bias = "neutral"
            lines.append(f"- COT Net Position: {cot:.2f} ({bias})")

        # Social sentiment
        social = sil_data.get("sil_social_bullish_ratio")
        if social is not None:
            lines.append(f"- Social Sentiment: {social:.0%} bullish")

        # Alpha Vantage sentiment
        alpha = sil_data.get("sil_alpha_sentiment_score")
        if alpha is not None:
            lines.append(f"- News Sentiment: {alpha:+.2f}")

        # Composite
        comp = sil_data.get("sil_composite_score")
        if comp is not None:
            lines.append(f"- SIL Composite: {comp:+.2f}")

        return "\n".join(lines)

    def _format_memory_section(self, memory: MemoryContext) -> str:
        """Format memory context for agents."""
        lines = ["## Memory Context"]

        lines.append(f"- Recent win rate (24h): {memory.recent_win_rate:.0%}")
        lines.append(
            f"- STM items: {memory.stm_item_count}, " f"LTM patterns: {memory.ltm_pattern_count}"
        )

        if memory.similar_patterns:
            lines.append("- Similar historical patterns:")
            for p in memory.similar_patterns[:3]:
                lines.append(
                    f"  - {p.description} "
                    f"(confidence={p.confidence:.2f}, avg_outcome={p.avg_outcome:+.4f})"
                )

        if memory.episodic_warnings:
            lines.append("- WARNINGS from past episodes:")
            for w in memory.episodic_warnings:
                lines.append(f"  - ⚠ {w.description}: {w.lesson} (action={w.recommended_action})")

        if memory.blacklist_conditions:
            lines.append(f"- {len(memory.blacklist_conditions)} active blacklist conditions")

        return "\n".join(lines)

    def _truncate_sections(self, sections: list[str], max_tokens: int) -> list[str]:
        """Truncate sections to fit within token budget. Prioritize news > macro > memory."""
        max_chars = max_tokens * 4
        result = []
        remaining = max_chars

        for section in sections:
            if len(section) <= remaining:
                result.append(section)
                remaining -= len(section)
            elif remaining > 100:  # only truncate if meaningful space left
                result.append(section[: remaining - 3] + "...")
                remaining = 0

            if remaining <= 0:
                break

        return result
