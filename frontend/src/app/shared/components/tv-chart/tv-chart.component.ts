import {
  Component, ElementRef, Input, OnDestroy, OnChanges,
  SimpleChanges, ViewChild, AfterViewInit,
} from '@angular/core';
import {
  createChart, IChartApi, ISeriesApi,
  CandlestickSeries, LineSeries, AreaSeries, HistogramSeries,
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

@Component({
  selector: 'app-tv-chart',
  standalone: true,
  template: `<div #chartContainer [style.height.px]="height"></div>`,
})
export class TvChartComponent implements AfterViewInit, OnChanges, OnDestroy {
  @ViewChild('chartContainer') chartContainer!: ElementRef<HTMLDivElement>;

  @Input() mode: ChartMode = 'candlestick';
  @Input() ohlcData: OhlcDataPoint[] = [];
  @Input() lineData: LineDataPoint[] = [];
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
  }
}
