# MANTIS-EVOLUTION: Chart Generator for Vision AI
"""
Generates annotated financial charts as PNG bytes for vision analysis.

Uses matplotlib with the non-interactive Agg backend so it works in
headless server environments. Does NOT depend on mplfinance.

If matplotlib is unavailable a minimal valid 1×1 PNG is returned as a
safe fallback so callers never receive None or an exception.
"""
from __future__ import annotations

import hashlib
import io
import struct
import zlib
from typing import Any

import numpy as np
from loguru import logger

from src.vision.schemas import ChartConfig

# ---------------------------------------------------------------------------
# Optional matplotlib import — graceful degradation if not installed
# ---------------------------------------------------------------------------
try:
    import matplotlib

    matplotlib.use("Agg")  # Non-interactive backend, must be set before pyplot
    import matplotlib.pyplot as plt

    HAS_MATPLOTLIB = True
except ImportError:  # pragma: no cover
    HAS_MATPLOTLIB = False


class MantisChartGenerator:
    """
    Generates annotated trading charts as PNG bytes.

    Uses matplotlib with Agg backend (no display needed).
    If matplotlib is not available, or if chart rendering fails for any
    reason, returns a minimal valid PNG so callers are never blocked.

    Usage::

        gen = MantisChartGenerator()
        png_bytes = gen.generate(dates, opens, highs, lows, closes,
                                 volumes=vols, indicators=inds, title="XAUUSD")
        chart_hash = gen.get_chart_hash(png_bytes)
    """

    def __init__(self, config: ChartConfig | None = None) -> None:
        self.config = config or ChartConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        dates: list | np.ndarray,
        opens: list | np.ndarray,
        highs: list | np.ndarray,
        lows: list | np.ndarray,
        closes: list | np.ndarray,
        volumes: list | np.ndarray | None = None,
        indicators: dict[str, Any] | None = None,
        title: str = "",
    ) -> bytes:
        """
        Generate a chart as PNG bytes.

        Args:
            dates:    Timestamps or integer indices (used as x-axis labels).
            opens:    Open prices.
            highs:    High prices.
            lows:     Low prices.
            closes:   Close prices.
            volumes:  Optional volume data.  Rendered in a sub-panel when
                      ``config.show_volume`` is True.
            indicators: Optional dict with pre-computed arrays.  Recognised
                        keys: ``ema_9``, ``ema_21``, ``bb_upper``,
                        ``bb_lower``, ``rsi_14``.
            title:    Chart title string.

        Returns:
            PNG bytes.  Never raises — falls back to :meth:`_minimal_png`.
        """
        if not HAS_MATPLOTLIB:  # pragma: no cover
            return self._minimal_png()

        # Empty data guard — matplotlib will raise on 0-length arrays
        closes_arr = np.asarray(closes, dtype=float)
        if closes_arr.size == 0:
            return self._minimal_png()

        try:
            return self._render_chart(
                dates,
                opens,
                highs,
                lows,
                closes,
                volumes,
                indicators or {},
                title,
            )
        except Exception as exc:
            logger.warning(f"Chart generation failed: {exc!r}")
            return self._minimal_png()

    def get_chart_hash(self, png_bytes: bytes) -> str:
        """Return a 16-character hex digest (truncated SHA-256) of *png_bytes*.

        Useful for deduplication — identical market data snapshots produce
        identical charts and therefore identical hashes.
        """
        return hashlib.sha256(png_bytes).hexdigest()[:16]

    # ------------------------------------------------------------------
    # Private rendering helpers
    # ------------------------------------------------------------------

    def _render_chart(
        self,
        dates,
        opens,
        highs,
        lows,
        closes,
        volumes,
        indicators: dict[str, Any],
        title: str,
    ) -> bytes:
        """Render the full chart using matplotlib and return PNG bytes."""
        closes_arr = np.asarray(closes, dtype=float)
        opens_arr = np.asarray(opens, dtype=float)
        highs_arr = np.asarray(highs, dtype=float)
        lows_arr = np.asarray(lows, dtype=float)
        x = np.arange(len(closes_arr))

        # Determine subplot layout
        has_volume = volumes is not None and self.config.show_volume
        has_rsi = self.config.show_rsi and "rsi_14" in indicators
        n_subplots = 1 + int(has_volume) + int(has_rsi)

        fig, axes = plt.subplots(
            n_subplots,
            1,
            figsize=(self.config.width / 100, self.config.height / 100),
            gridspec_kw={"height_ratios": self._get_ratios(n_subplots)},
            sharex=True,
        )

        # Normalise axes to always be a list
        if n_subplots == 1:
            axes = [axes]

        # Global figure background
        fig.patch.set_facecolor("#0d1117")

        # ---- Price panel ------------------------------------------------
        ax_price = axes[0]
        ax_price.set_facecolor("#0d1117")
        ax_price.tick_params(colors="#8B949E")
        for spine in ax_price.spines.values():
            spine.set_edgecolor("#21262d")

        # Bullish / bearish split
        up = closes_arr >= opens_arr
        down = ~up

        # Up candles — MANTIS neon green
        if up.any():
            ax_price.bar(
                x[up],
                closes_arr[up] - opens_arr[up],
                bottom=opens_arr[up],
                color="#39FF14",
                width=0.6,
                alpha=0.9,
            )
            ax_price.vlines(
                x[up], lows_arr[up], highs_arr[up], color="#39FF14", linewidth=0.5
            )

        # Down candles — MANTIS loss red
        if down.any():
            ax_price.bar(
                x[down],
                opens_arr[down] - closes_arr[down],
                bottom=closes_arr[down],
                color="#FF3D57",
                width=0.6,
                alpha=0.9,
            )
            ax_price.vlines(
                x[down], lows_arr[down], highs_arr[down], color="#FF3D57", linewidth=0.5
            )

        # EMA overlays
        if self.config.show_ema:
            if "ema_9" in indicators:
                ax_price.plot(
                    x,
                    indicators["ema_9"],
                    color="#00E5FF",
                    linewidth=1,
                    alpha=0.7,
                    label="EMA 9",
                )
            if "ema_21" in indicators:
                ax_price.plot(
                    x,
                    indicators["ema_21"],
                    color="#FFB020",
                    linewidth=1,
                    alpha=0.7,
                    label="EMA 21",
                )

        # Bollinger Bands
        if self.config.show_bollinger:
            if "bb_upper" in indicators and "bb_lower" in indicators:
                ax_price.plot(
                    x,
                    indicators["bb_upper"],
                    color="#8B949E",
                    linewidth=0.5,
                    linestyle="--",
                    alpha=0.5,
                )
                ax_price.plot(
                    x,
                    indicators["bb_lower"],
                    color="#8B949E",
                    linewidth=0.5,
                    linestyle="--",
                    alpha=0.5,
                )
                ax_price.fill_between(
                    x,
                    indicators["bb_lower"],
                    indicators["bb_upper"],
                    color="#8B949E",
                    alpha=0.05,
                )

        ax_price.set_title(
            title or "MANTIS Chart", color="#e6edf3", fontsize=10, pad=6
        )
        handles, labels = ax_price.get_legend_handles_labels()
        if handles:
            ax_price.legend(
                loc="upper left",
                fontsize=7,
                facecolor="#161b22",
                edgecolor="#8B949E",
                labelcolor="#e6edf3",
            )

        subplot_idx = 1

        # ---- Volume panel -----------------------------------------------
        if has_volume and subplot_idx < n_subplots:
            ax_vol = axes[subplot_idx]
            ax_vol.set_facecolor("#0d1117")
            ax_vol.tick_params(colors="#8B949E")
            for spine in ax_vol.spines.values():
                spine.set_edgecolor("#21262d")
            vols = np.asarray(volumes, dtype=float)
            bar_colors = [
                "#39FF14" if c >= o else "#FF3D57"
                for c, o in zip(closes_arr, opens_arr)
            ]
            ax_vol.bar(x, vols, color=bar_colors, alpha=0.5, width=0.6)
            ax_vol.set_ylabel("Volume", color="#8B949E", fontsize=8)
            subplot_idx += 1

        # ---- RSI panel --------------------------------------------------
        if has_rsi and subplot_idx < n_subplots:
            ax_rsi = axes[subplot_idx]
            ax_rsi.set_facecolor("#0d1117")
            ax_rsi.tick_params(colors="#8B949E")
            for spine in ax_rsi.spines.values():
                spine.set_edgecolor("#21262d")
            ax_rsi.plot(x, indicators["rsi_14"], color="#00E5FF", linewidth=1)
            ax_rsi.axhline(70, color="#FF3D57", linewidth=0.5, linestyle="--", alpha=0.5)
            ax_rsi.axhline(30, color="#39FF14", linewidth=0.5, linestyle="--", alpha=0.5)
            ax_rsi.set_ylim(0, 100)
            ax_rsi.set_ylabel("RSI", color="#8B949E", fontsize=8)

        plt.tight_layout(pad=0.5)

        buf = io.BytesIO()
        fig.savefig(
            buf,
            format="png",
            dpi=100,
            bbox_inches="tight",
            facecolor=fig.get_facecolor(),
        )
        plt.close(fig)
        buf.seek(0)
        return buf.read()

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------

    def _get_ratios(self, n: int) -> list[int]:
        """Return gridspec height ratios for *n* subplots."""
        if n == 1:
            return [1]
        if n == 2:
            return [3, 1]
        return [3, 1, 1]  # price : volume : RSI

    # ------------------------------------------------------------------
    # Fallback PNG
    # ------------------------------------------------------------------

    @staticmethod
    def _minimal_png() -> bytes:
        """Return a minimal valid 1×1 white PNG.

        Used as a safe fallback when matplotlib is unavailable or when
        chart rendering raises an unexpected exception.  The returned
        bytes are always a structurally valid PNG file.
        """
        # PNG structure: signature + IHDR chunk + IDAT chunk + IEND chunk
        PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

        def _make_chunk(chunk_type: bytes, data: bytes) -> bytes:
            payload = chunk_type + data
            crc = zlib.crc32(payload) & 0xFFFFFFFF
            return struct.pack(">I", len(data)) + payload + struct.pack(">I", crc)

        # IHDR: width=1, height=1, bit_depth=8, color_type=2 (RGB), …
        ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)

        # IDAT: single row, filter byte 0x00 + 3 bytes (R=0, G=0, B=0)
        raw_row = b"\x00\x00\x00\x00"  # filter + 1 RGB pixel (black)
        idat_data = zlib.compress(raw_row)

        return (
            PNG_SIGNATURE
            + _make_chunk(b"IHDR", ihdr_data)
            + _make_chunk(b"IDAT", idat_data)
            + _make_chunk(b"IEND", b"")
        )
