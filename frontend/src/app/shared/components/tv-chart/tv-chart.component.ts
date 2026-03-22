import {
  Component, ElementRef, Input, OnDestroy, OnChanges,
  SimpleChanges, ViewChild, AfterViewInit,
} from '@angular/core';
import {
  createChart, IChartApi, ISeriesApi,
  CandlestickSeries, LineSeries, AreaSeries, HistogramSeries, BaselineSeries,
  CandlestickData, LineData, HistogramData, Time,
} from 'lightweight-charts';

export type ChartMode = 'candlestick' | 'area' | 'line';

export interface OhlcDataPoint {
  time: string | number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

export interface LineDataPoint {
  time: string | number;
  value: number;
}

export interface EquityTooltipPoint {
  date: string;
  equity: number;
  daily_pnl: number;
  drawdown_pct: number;
  trade_count: number;
  win_count: number;
  cumulative_trades: number;
  cumulative_win_rate: number;
}

@Component({
  selector: 'app-tv-chart',
  standalone: true,
  template: `
    <div style="position: relative; overflow: hidden;">
      <div #chartContainer [style.height.px]="height"></div>
      <div #tooltipEl class="tv-chart-tooltip"></div>
    </div>
  `,
  styles: [`
    .tv-chart-tooltip {
      display: none;
      position: absolute;
      top: 12px;
      left: 12px;
      z-index: 10;
      pointer-events: none;
      background: rgba(13, 17, 23, 0.92);
      border: 1px solid rgba(255, 255, 255, 0.10);
      border-radius: 8px;
      padding: 10px 14px;
      font-family: 'IBM Plex Mono', monospace;
      font-size: 0.72rem;
      color: #c9d1d9;
      backdrop-filter: blur(8px);
      min-width: 185px;
      line-height: 1.65;
    }
  `]
})
export class TvChartComponent implements AfterViewInit, OnChanges, OnDestroy {
  @ViewChild('chartContainer') chartContainer!: ElementRef<HTMLDivElement>;
  @ViewChild('tooltipEl') tooltipRef!: ElementRef<HTMLDivElement>;

  @Input() mode: ChartMode = 'candlestick';
  @Input() ohlcData: OhlcDataPoint[] = [];
  @Input() lineData: LineDataPoint[] = [];
  @Input() drawdownData: LineDataPoint[] = [];
  @Input() equityTooltipData: EquityTooltipPoint[] = [];
  @Input() showVolume = false;
  @Input() height = 400;
  @Input() lineColor = '#00d97e';
  @Input() areaTopColor = 'rgba(0, 217, 126, 0.25)';
  @Input() areaBottomColor = 'rgba(0, 217, 126, 0.02)';
  @Input() upColor = '#00d97e';
  @Input() downColor = '#ef5350';
  @Input() autoFit = true;

  private chart: IChartApi | null = null;
  private mainSeries: ISeriesApi<any> | null = null;
  private volumeSeries: ISeriesApi<any> | null = null;
  private drawdownSeries: ISeriesApi<any> | null = null;
  private tooltipMap = new Map<string, EquityTooltipPoint>();
  private tooltipSubscribed = false;
  private resizeObserver: ResizeObserver | null = null;

  ngAfterViewInit(): void {
    this.createChartInstance();
    this.updateData();
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (!this.chart) return;

    const needsRecreate = changes['mode'] || changes['showVolume'];
    if (needsRecreate) {
      this.destroyChart();
      this.createChartInstance();
    }
    this.updateData();
  }

  ngOnDestroy(): void {
    this.destroyChart();
  }

  private createChartInstance(): void {
    if (!this.chartContainer?.nativeElement) return;

    const container = this.chartContainer.nativeElement;
    this.chart = createChart(container, {
      width: container.clientWidth,
      height: this.height,
      layout: {
        background: { color: 'transparent' } as any,
        textColor: '#7d8590',
        fontFamily: "'Inter', -apple-system, sans-serif",
      },
      grid: {
        vertLines: { color: 'rgba(0, 217, 126, 0.03)' },
        horzLines: { color: 'rgba(0, 217, 126, 0.03)' },
      },
      crosshair: {
        mode: 0,
        vertLine: { color: 'rgba(0, 217, 126, 0.3)', style: 2, width: 1, labelVisible: true },
        horzLine: { color: 'rgba(0, 217, 126, 0.3)', style: 2, width: 1, labelVisible: true },
      },
      rightPriceScale: {
        borderColor: 'rgba(0, 217, 126, 0.08)',
        scaleMargins: this.showVolume
          ? { top: 0.05, bottom: 0.25 }
          : { top: 0.05, bottom: 0.05 },
      },
      timeScale: {
        borderColor: 'rgba(0, 217, 126, 0.08)',
        timeVisible: true,
        secondsVisible: false,
      },
    });

    // Main series
    if (this.mode === 'candlestick') {
      this.mainSeries = this.chart.addSeries(CandlestickSeries, {
        upColor: this.upColor,
        downColor: this.downColor,
        borderVisible: false,
        wickUpColor: this.upColor,
        wickDownColor: this.downColor,
      });
    } else if (this.mode === 'area') {
      this.mainSeries = this.chart.addSeries(AreaSeries, {
        lineColor: this.lineColor,
        topColor: this.areaTopColor,
        bottomColor: this.areaBottomColor,
        lineWidth: 2,
      });
    } else {
      this.mainSeries = this.chart.addSeries(LineSeries, {
        color: this.lineColor,
        lineWidth: 2,
      });
    }

    // Volume histogram
    if (this.showVolume && this.mode === 'candlestick') {
      this.volumeSeries = this.chart.addSeries(HistogramSeries, {
        color: 'rgba(100, 100, 100, 0.5)',
        priceFormat: { type: 'volume' },
        priceScaleId: 'volume',
      });
      this.chart.priceScale('volume').applyOptions({
        scaleMargins: { top: 0.8, bottom: 0 },
      });
    }

    // Resize observer
    this.resizeObserver = new ResizeObserver(() => {
      if (this.chart && container.clientWidth > 0) {
        this.chart.applyOptions({ width: container.clientWidth });
      }
    });
    this.resizeObserver.observe(container);
  }

  private ensureDrawdownSeries(): void {
    if (this.drawdownSeries || !this.chart || this.mode !== 'area') return;

    this.drawdownSeries = this.chart.addSeries(BaselineSeries, {
      baseValue: { type: 'price', price: 0 },
      topLineColor: 'transparent',
      topFillColor1: 'transparent',
      topFillColor2: 'transparent',
      bottomLineColor: 'rgba(255, 61, 87, 0.5)',
      bottomFillColor1: 'rgba(255, 61, 87, 0.22)',
      bottomFillColor2: 'rgba(255, 61, 87, 0.02)',
      lineWidth: 1,
      priceScaleId: 'drawdown',
      priceFormat: {
        type: 'custom',
        formatter: (p: number) => p.toFixed(1) + '%',
        minMove: 0.01,
      },
      crosshairMarkerVisible: false,
    } as any);

    this.chart.priceScale('drawdown').applyOptions({
      scaleMargins: { top: 0.0, bottom: 0.0 },
      visible: false,
    });
  }

  private ensureTooltip(): void {
    if (this.tooltipSubscribed || !this.chart) return;
    this.tooltipSubscribed = true;

    this.chart.subscribeCrosshairMove((param) => {
      const tooltip = this.tooltipRef?.nativeElement;
      if (!tooltip) return;

      if (!param.time || this.tooltipMap.size === 0) {
        tooltip.style.display = 'none';
        return;
      }

      const timeStr = String(param.time);
      const data = this.tooltipMap.get(timeStr);
      if (!data) {
        tooltip.style.display = 'none';
        return;
      }

      const pnlColor = data.daily_pnl >= 0 ? '#39FF14' : '#FF3D57';
      const pnlSign = data.daily_pnl >= 0 ? '+' : '';
      const ddColor = data.drawdown_pct < 0 ? '#FF3D57' : '#7d8590';
      const wrPct = (data.cumulative_win_rate * 100).toFixed(1);
      const eqStr = data.equity.toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      });
      const losses = data.trade_count - data.win_count;

      tooltip.innerHTML =
        `<div style="color:#e6edf3;font-weight:600;margin-bottom:4px;border-bottom:1px solid rgba(255,255,255,0.08);padding-bottom:4px;">${data.date}</div>` +
        `<div><span style="color:#7d8590;">Equity</span> <span style="color:#e6edf3;">$ ${eqStr}</span></div>` +
        `<div><span style="color:#7d8590;">Daily P&L</span> <span style="color:${pnlColor};">${pnlSign}$ ${Math.abs(data.daily_pnl).toFixed(2)}</span></div>` +
        `<div><span style="color:#7d8590;">Drawdown</span> <span style="color:${ddColor};">${data.drawdown_pct.toFixed(2)}%</span></div>` +
        `<div><span style="color:#7d8590;">Trades</span> ${data.trade_count} <span style="color:#7d8590;">(${data.win_count}W ${losses}L)</span></div>` +
        `<div><span style="color:#7d8590;">Win Rate</span> ${wrPct}% <span style="color:#7d8590;">(${data.cumulative_trades} tot)</span></div>`;

      tooltip.style.display = 'block';
    });
  }

  private updateData(): void {
    if (!this.mainSeries) return;

    if (this.mode === 'candlestick' && this.ohlcData.length > 0) {
      const candleData: CandlestickData[] = this.ohlcData.map(d => ({
        time: d.time as Time,
        open: d.open,
        high: d.high,
        low: d.low,
        close: d.close,
      }));
      this.mainSeries.setData(candleData);

      if (this.volumeSeries) {
        const volData: HistogramData[] = this.ohlcData
          .filter(d => d.volume != null)
          .map(d => ({
            time: d.time as Time,
            value: d.volume!,
            color: d.close >= d.open
              ? 'rgba(38, 166, 154, 0.4)'
              : 'rgba(239, 83, 80, 0.4)',
          }));
        this.volumeSeries.setData(volData);
      }
    } else if (this.lineData.length > 0) {
      const data: LineData[] = this.lineData.map(d => ({
        time: d.time as Time,
        value: d.value,
      }));
      this.mainSeries.setData(data);
    }

    // Drawdown overlay (lazy creation)
    if (this.mode === 'area' && this.drawdownData.length > 0 && this.chart) {
      this.ensureDrawdownSeries();
      if (this.drawdownSeries) {
        const ddData: LineData[] = this.drawdownData.map(d => ({
          time: d.time as Time,
          value: d.value,
        }));
        this.drawdownSeries.setData(ddData);
      }
    }

    // Build tooltip lookup map
    if (this.equityTooltipData.length > 0) {
      this.tooltipMap.clear();
      for (const pt of this.equityTooltipData) {
        this.tooltipMap.set(pt.date, pt);
      }
      this.ensureTooltip();
    }

    if (this.autoFit && this.chart) {
      this.chart.timeScale().fitContent();
    }
  }

  private destroyChart(): void {
    this.resizeObserver?.disconnect();
    this.resizeObserver = null;
    this.chart?.remove();
    this.chart = null;
    this.mainSeries = null;
    this.volumeSeries = null;
    this.drawdownSeries = null;
    this.tooltipSubscribed = false;
  }
}
