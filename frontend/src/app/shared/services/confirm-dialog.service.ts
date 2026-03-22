import { Injectable, signal } from '@angular/core';

export interface ConfirmDialogOptions {
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  color?: 'danger' | 'warning' | 'primary' | 'info';
  icon?: string;
}

@Injectable({ providedIn: 'root' })
export class ConfirmDialogService {
  readonly visible = signal(false);
  readonly options = signal<ConfirmDialogOptions>({
    title: '',
    message: '',
  });

  private resolveRef: ((value: boolean) => void) | null = null;

  confirm(opts: ConfirmDialogOptions): Promise<boolean> {
    this.options.set({
      confirmText: 'Conferma',
      cancelText: 'Annulla',
      color: 'danger',
      ...opts,
    });
    this.visible.set(true);

    return new Promise<boolean>((resolve) => {
      this.resolveRef = resolve;
    });
  }

  /** Called by the dialog component */
  resolve(result: boolean): void {
    this.visible.set(false);
    if (this.resolveRef) {
      this.resolveRef(result);
      this.resolveRef = null;
    }
  }
}
