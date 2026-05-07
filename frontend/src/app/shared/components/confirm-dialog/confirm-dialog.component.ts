import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  ModalComponent, ModalHeaderComponent, ModalBodyComponent,
  ModalFooterComponent,
} from '@coreui/angular';
import { IconDirective } from '@coreui/icons-angular';
import { ConfirmDialogService } from '../../services/confirm-dialog.service';

type DialogColor = 'danger' | 'warning' | 'primary' | 'info';

@Component({
  selector: 'app-confirm-dialog',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule, ModalComponent, ModalHeaderComponent, ModalBodyComponent,
    ModalFooterComponent, IconDirective,
  ],
  template: `
    <c-modal
      class="mantis-confirm"
      [visible]="dialogService.visible()"
      (visibleChange)="onVisibleChange($event)"
      alignment="center"
      backdrop="static"
      [keyboard]="false"
    >
      <c-modal-header class="mantis-confirm__header">
        <div class="mantis-confirm__icon mantis-confirm__icon--{{ variant() }}" aria-hidden="true">
          @if (dialogService.options().icon) {
            <svg [cIcon]="dialogService.options().icon!" size="lg"></svg>
          } @else {
            {{ glyph() }}
          }
        </div>
        <h5 class="mantis-confirm__title">{{ dialogService.options().title }}</h5>
      </c-modal-header>

      <c-modal-body class="mantis-confirm__body">
        <p class="mantis-confirm__message">{{ dialogService.options().message }}</p>
      </c-modal-body>

      <c-modal-footer class="mantis-confirm__footer">
        <button
          type="button"
          class="mantis-btn mantis-btn--ghost"
          (click)="dialogService.resolve(false)"
        >
          {{ dialogService.options().cancelText }}
        </button>
        <button
          type="button"
          class="mantis-btn mantis-btn--{{ variant() }}"
          (click)="dialogService.resolve(true)"
        >
          {{ dialogService.options().confirmText }}
        </button>
      </c-modal-footer>
    </c-modal>
  `,
  styleUrls: ['./confirm-dialog.component.scss'],
})
export class ConfirmDialogComponent {
  readonly dialogService = inject(ConfirmDialogService);

  readonly variant = computed<DialogColor>(
    () => (this.dialogService.options().color ?? 'danger') as DialogColor,
  );

  readonly glyph = computed<string>(() => {
    switch (this.variant()) {
      case 'danger':  return '✕';
      case 'warning': return '⚠';
      case 'primary': return '✓';
      case 'info':    return 'ⓘ';
    }
  });

  onVisibleChange(visible: boolean): void {
    if (!visible) {
      this.dialogService.resolve(false);
    }
  }
}
