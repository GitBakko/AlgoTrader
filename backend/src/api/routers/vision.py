# MANTIS-EVOLUTION: Vision AI + RAG API Router
"""
Vision AI and RAG Pipeline API endpoints.

Endpoints:
  GET  /api/vision/status     — Vision + RAG pipeline status
  POST /api/vision/chart      — Generate chart PNG for an asset
  POST /api/vision/analyze    — Run vision analysis on an asset
  GET  /api/vision/rag        — Get current RAG context for an asset
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from loguru import logger

from src.agents.schemas import MarketContext
from src.utils.config import get_settings
from src.vision.chart_generator import MantisChartGenerator
from src.vision.schemas import ChartConfig

router = APIRouter()


def _success(data):
    return {"success": True, "data": data}


def _error(msg: str, status: int = 400):
    return {"success": False, "error": msg}


@router.get("/status")
async def vision_status():
    """Get Vision AI and RAG pipeline status."""
    settings = get_settings()
    return _success(
        {
            "vision_enabled": settings.vision_enabled,
            "rag_enabled": settings.rag_enabled,
            "vision_model": settings.vision_llm_model,
            "chart_width": settings.vision_chart_width,
            "chart_height": settings.vision_chart_height,
            "rag_max_tokens": settings.rag_max_context_tokens,
            "rag_news_lookback_hours": settings.rag_news_lookback_hours,
        }
    )


@router.post("/chart")
async def generate_chart(
    request: Request,
    epic: str = Query(..., description="Asset epic (e.g., XAUUSD)"),
):
    """
    Generate a chart PNG for the given asset.
    Returns image/png bytes.
    """
    settings = get_settings()
    loop = getattr(request.app.state, "paper_loop", None)

    # Get OHLC data from the loop's data store if available
    config = ChartConfig(
        width=settings.vision_chart_width,
        height=settings.vision_chart_height,
    )
    generator = MantisChartGenerator(config=config)

    # Try to get real data from the trading loop
    closes = []
    opens = []
    highs = []
    lows = []
    volumes = []
    title = f"{epic} — Chart"

    if loop is not None:
        try:
            data_store = getattr(loop, "data_store", None) or getattr(loop, "_data_store", None)
            if data_store is not None:
                df = await data_store.get_latest(epic, bars=100)
                if df is not None and len(df) > 0:
                    opens = df["open"].to_list() if "open" in df.columns else []
                    highs = df["high"].to_list() if "high" in df.columns else []
                    lows = df["low"].to_list() if "low" in df.columns else []
                    closes = df["close"].to_list() if "close" in df.columns else []
                    volumes = df["volume"].to_list() if "volume" in df.columns else []
        except Exception as e:
            logger.debug(f"Could not get OHLC from data store: {e!r}")

    if not closes:
        # Fallback: generate synthetic chart
        import numpy as np

        n = 50
        np.random.seed(hash(epic) % 2**31)
        noise = np.random.randn(n) * 0.5
        base = 100.0
        closes = list(base + np.cumsum(noise))
        opens = [c - np.random.rand() * 0.3 for c in closes]
        highs = [max(o, c) + np.random.rand() * 0.5 for o, c in zip(opens, closes)]
        lows = [min(o, c) - np.random.rand() * 0.5 for o, c in zip(opens, closes)]
        title = f"{epic} — Synthetic Chart"

    png_bytes = generator.generate(
        dates=list(range(len(closes))),
        opens=opens,
        highs=highs,
        lows=lows,
        closes=closes,
        volumes=volumes or None,
        title=title,
    )

    return Response(content=png_bytes, media_type="image/png")


@router.post("/analyze")
async def analyze_chart(
    epic: str = Query(..., description="Asset epic (e.g., XAUUSD)"),
):
    """
    Run full Vision AI analysis on an asset's chart.
    Requires VISION_ENABLED=true.
    """
    settings = get_settings()
    if not settings.vision_enabled:
        return _error("Vision AI is disabled. Set VISION_ENABLED=true to enable.", 403)

    try:
        from src.agents.vision_agent import VisionAgent

        agent = VisionAgent(
            vision_model=settings.vision_llm_model,
            chart_config=ChartConfig(
                width=settings.vision_chart_width,
                height=settings.vision_chart_height,
            ),
            rag_max_tokens=settings.rag_max_context_tokens,
            news_lookback_hours=settings.rag_news_lookback_hours,
        )

        context = MarketContext(
            epic=epic,
            current_price=0.0,  # Will be filled from synthetic data
            atr=1.0,
        )

        result = await agent.analyze(context)
        return _success(
            {
                "epic": epic,
                "vision_report": (
                    result.vision_report.model_dump() if result.vision_report else None
                ),
                "rag_context_summary": result.rag_context_summary,
                "chart_confidence": result.chart_confidence,
            }
        )
    except Exception as e:
        logger.error(f"Vision analysis failed: {e!r}")
        return _error(f"Vision analysis failed: {e}")


@router.get("/rag")
async def get_rag_context(
    request: Request,
    epic: str = Query(..., description="Asset epic (e.g., XAUUSD)"),
):
    """
    Get current RAG context for an asset.
    Requires RAG_ENABLED=true.
    """
    settings = get_settings()
    if not settings.rag_enabled:
        return _error("RAG pipeline is disabled. Set RAG_ENABLED=true to enable.", 403)

    try:
        from src.rag.context_builder import MantisRAGContextBuilder
        from src.rag.news_ingester import MantisNewsIngester

        loop = getattr(request.app.state, "paper_loop", None)
        sil_data = {}

        if loop is not None:
            sil = getattr(loop, "_sil_data", None)
            if sil is not None:
                sil_data = sil.model_dump() if hasattr(sil, "model_dump") else {}

        ingester = MantisNewsIngester(lookback_hours=settings.rag_news_lookback_hours)
        news_items = ingester.ingest(sil_data.get("news", []), symbol=epic)

        builder = MantisRAGContextBuilder(max_tokens=settings.rag_max_context_tokens)
        rag = builder.build(news=news_items, sil_data=sil_data.get("macro"))

        return _success(
            {
                "epic": epic,
                "news_section": rag.news_section,
                "macro_section": rag.macro_section,
                "memory_section": rag.memory_section,
                "total_tokens_estimate": rag.total_tokens_estimate,
                "sources_count": rag.sources_count,
            }
        )
    except Exception as e:
        logger.error(f"RAG context build failed: {e!r}")
        return _error(f"RAG context build failed: {e}")
