import { Component, input, model, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { DropdownModule, BadgeModule } from '@coreui/angular';

export interface MarketStatus {
  is_open: boolean;
  status: string;
  next_open: number | null;
}

@Component({
  selector: 'app-epic-selector',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, DropdownModule, BadgeModule],
  templateUrl: './epic-selector.component.html',
  styleUrl: './epic-selector.component.scss'
})
export class EpicSelectorComponent {
  epics = input<string[]>([]);
  selectedEpic = model<string | null>(null);
  marketStatus = input<Record<string, MarketStatus>>({});

  onSelect(epic: string): void {
    this.selectedEpic.set(epic);
  }
}
