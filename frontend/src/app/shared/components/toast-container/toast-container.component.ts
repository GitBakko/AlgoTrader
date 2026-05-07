import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ToasterComponent } from '@coreui/angular';
import { ToastService, ToastMessage } from '../../services/toast.service';

type ToastVariant = 'success' | 'info' | 'warning' | 'error';

interface ToastView extends ToastMessage {
  variant: ToastVariant;
  icon: string;
  ariaLabel: string;
}

const MAX_VISIBLE = 4;

@Component({
  selector: 'app-toast-container',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, ToasterComponent],
  template: `
    <c-toaster placement="top-end" class="mantis-toaster" position="fixed">
      @for (toast of visibleToasts(); track toast.id) {
        <div
          class="mantis-toast mantis-toast--{{ toast.variant }}"
          role="alert"
          aria-live="polite"
        >
          <span class="mantis-toast__icon" aria-hidden="true">{{ toast.icon }}</span>
          <span class="mantis-toast__text">{{ toast.text }}</span>
          <button
            type="button"
            class="mantis-toast__close"
            [attr.aria-label]="toast.ariaLabel"
            (click)="toastService.dismiss(toast.id)"
          >
            &times;
          </button>
        </div>
      }
    </c-toaster>
  `,
  styleUrls: ['./toast-container.component.scss'],
})
export class ToastContainerComponent {
  readonly toastService = inject(ToastService);

  readonly visibleToasts = computed<ToastView[]>(() => {
    const list = this.toastService.toasts();
    const slice = list.slice(-MAX_VISIBLE);
    return slice.map((t) => ({
      ...t,
      variant: this.toVariant(t.color),
      icon: this.toIcon(t.color),
      ariaLabel: 'Chiudi notifica',
    }));
  });

  private toVariant(color: ToastMessage['color']): ToastVariant {
    switch (color) {
      case 'success': return 'success';
      case 'danger':  return 'error';
      case 'warning': return 'warning';
      case 'info':
      case 'primary':
      default:        return 'info';
    }
  }

  private toIcon(color: ToastMessage['color']): string {
    // Glyph chosen so the icon never collides visually with the close X.
    // Error uses `!` (bold exclamation) instead of × so users don't try to
    // dismiss a toast by clicking the status icon.
    switch (color) {
      case 'success': return '✓';
      case 'danger':  return '!';
      case 'warning': return '⚠';
      case 'info':
      case 'primary':
      default:        return 'i';
    }
  }
}
