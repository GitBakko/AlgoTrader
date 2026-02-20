import { Component, ChangeDetectionStrategy, input, computed } from '@angular/core';
import { CommonModule } from '@angular/common';

export interface CorrelationData {
  epics: string[];
  matrix: number[][];
  period_days: number;
  data_points: number;
}

@Component({
  selector: 'app-correlation-heatmap',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule],
  styles: [`
    .heatmap-container {
      overflow: auto;
      max-width: 100%;
    }
    .heatmap-grid {
      display: inline-grid;
      gap: 1px;
    }
    .heatmap-cell {
      width: 36px;
      height: 36px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 0.6rem;
      font-family: 'IBM Plex Mono', monospace;
      cursor: default;
      border-radius: 2px;
      position: relative;
    }
    .heatmap-cell:hover {
      outline: 1px solid rgba(255,255,255,0.4);
      z-index: 1;
    }
    .heatmap-label-col {
      width: 60px;
      height: 36px;
      display: flex;
      align-items: center;
      justify-content: flex-end;
      padding-right: 6px;
      font-size: 0.625rem;
      font-weight: 600;
      color: rgba(255,255,255,0.7);
    }
    .heatmap-label-row {
      width: 36px;
      height: 40px;
      display: flex;
      align-items: flex-end;
      justify-content: center;
      font-size: 0.5625rem;
      font-weight: 600;
      color: rgba(255,255,255,0.7);
      writing-mode: vertical-lr;
      transform: rotate(180deg);
      padding-bottom: 4px;
    }
    .heatmap-corner {
      width: 60px;
      height: 40px;
    }
    .heatmap-info {
      font-size: 0.6875rem;
      color: rgba(255,255,255,0.5);
    }
  `],
  template: `
    @if (data()?.epics?.length) {
      <div class="heatmap-container">
        <div class="heatmap-grid" [style.grid-template-columns]="gridCols()">
          <!-- Header row: corner + column labels -->
          <div class="heatmap-corner"></div>
          @for (epic of data()!.epics; track epic) {
            <div class="heatmap-label-row">{{ epic }}</div>
          }
          <!-- Data rows -->
          @for (epic of data()!.epics; track epic; let i = $index) {
            <div class="heatmap-label-col">{{ epic }}</div>
            @for (val of data()!.matrix[i]; track $index; let j = $index) {
              <div class="heatmap-cell"
                   [style.background]="cellColor(val)"
                   [style.color]="textColor(val)"
                   [title]="data()!.epics[i] + ' / ' + data()!.epics[j] + ': ' + val.toFixed(3)">
                {{ i === j ? '' : val.toFixed(2) }}
              </div>
            }
          }
        </div>
      </div>
      <div class="heatmap-info mt-2">
        {{ data()!.data_points }} punti dati | {{ data()!.period_days }}g | Scala:
        <span style="color: #FF3D57">-1.0</span>
        <span> ... </span>
        <span style="color: rgba(255,255,255,0.5)">0.0</span>
        <span> ... </span>
        <span style="color: #39FF14">+1.0</span>
      </div>
    } @else {
      <div class="text-center py-4 text-body-secondary small">
        Nessun dato di correlazione disponibile
      </div>
    }
  `,
})
export class CorrelationHeatmapComponent {
  readonly data = input<CorrelationData | null>(null);

  readonly gridCols = computed(() => {
    const n = this.data()?.epics?.length ?? 0;
    return `60px repeat(${n}, 36px)`;
  });

  cellColor(val: number): string {
    if (val >= 0) {
      // 0 → transparent, +1 → green
      const alpha = Math.abs(val) * 0.7;
      return `rgba(57, 255, 20, ${alpha.toFixed(2)})`;
    } else {
      // 0 → transparent, -1 → red
      const alpha = Math.abs(val) * 0.7;
      return `rgba(255, 61, 87, ${alpha.toFixed(2)})`;
    }
  }

  textColor(val: number): string {
    return Math.abs(val) > 0.5 ? 'rgba(255,255,255,0.9)' : 'rgba(255,255,255,0.6)';
  }
}
