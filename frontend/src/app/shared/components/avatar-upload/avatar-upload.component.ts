import { Component, Output, EventEmitter, signal, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { AuthService } from '../../../core/services/auth.service';

/**
 * Avatar Upload Component
 * Drag-and-drop or click to upload avatar images
 * MANTIS AI - User profile picture upload with validation
 */
@Component({
  selector: 'app-avatar-upload',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="avatar-upload">
      <!-- Upload Zone -->
      <div
        class="avatar-upload__zone"
        [class.avatar-upload__zone--dragging]="isDragging()"
        [class.avatar-upload__zone--uploading]="isUploading()"
        [class.avatar-upload__zone--error]="error()"
        (dragover)="onDragOver($event)"
        (dragleave)="onDragLeave($event)"
        (drop)="onDrop($event)"
        (click)="fileInput.click()"
      >
        @if (isUploading()) {
          <div class="avatar-upload__spinner">
            <div class="spinner-border text-mantis" role="status">
              <span class="visually-hidden">Caricamento...</span>
            </div>
            <p class="mt-3 mb-0">Caricamento in corso...</p>
          </div>
        } @else {
          <div class="avatar-upload__content">
            <svg class="avatar-upload__icon" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
            <p class="avatar-upload__text">
              <strong>Clicca per caricare</strong> o trascina qui
            </p>
            <p class="avatar-upload__hint">
              JPG, PNG, GIF o WEBP (max 5MB)
            </p>
          </div>
        }

        <!-- Hidden File Input -->
        <input
          #fileInput
          type="file"
          accept="image/jpeg,image/png,image/gif,image/webp"
          (change)="onFileSelected($event)"
          class="avatar-upload__input"
        />
      </div>

      <!-- Error Message -->
      @if (error()) {
        <div class="alert alert-danger mt-3 mb-0" role="alert">
          <svg class="me-2" xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16">
            <path d="M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14zm0 1A8 8 0 1 0 8 0a8 8 0 0 0 0 16z"/>
            <path d="M7.002 11a1 1 0 1 1 2 0 1 1 0 0 1-2 0zM7.1 4.995a.905.905 0 1 1 1.8 0l-.35 3.507a.552.552 0 0 1-1.1 0L7.1 4.995z"/>
          </svg>
          {{ error() }}
        </div>
      }

      <!-- Success Message -->
      @if (success()) {
        <div class="alert alert-success mt-3 mb-0" role="alert">
          <svg class="me-2" xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16">
            <path d="M16 8A8 8 0 1 1 0 8a8 8 0 0 1 16 0zm-3.97-3.03a.75.75 0 0 0-1.08.022L7.477 9.417 5.384 7.323a.75.75 0 0 0-1.06 1.06L6.97 11.03a.75.75 0 0 0 1.079-.02l3.992-4.99a.75.75 0 0 0-.01-1.05z"/>
          </svg>
          Avatar caricato con successo!
        </div>
      }
    </div>
  `,
  styles: [`
    .avatar-upload {
      width: 100%;
    }

    .avatar-upload__zone {
      border: 2px dashed var(--mantis-border-accent);
      border-radius: var(--mantis-radius-md);
      padding: 2rem;
      text-align: center;
      cursor: pointer;
      transition: all 0.2s ease;
      background: var(--mantis-surface-2, rgba(22, 27, 34, 0.5));
      min-height: 200px;
      display: flex;
      align-items: center;
      justify-content: center;
    }

    .avatar-upload__zone:hover {
      border-color: var(--mantis-border-strong);
      background: var(--mantis-surface-2, rgba(22, 27, 34, 0.7));
    }

    .avatar-upload__zone--dragging {
      border-color: var(--mantis-neon);
      background: rgba(57, 255, 20, 0.1);
      box-shadow: 0 0 20px rgba(57, 255, 20, 0.2);
    }

    .avatar-upload__zone--uploading {
      cursor: not-allowed;
      opacity: 0.7;
    }

    .avatar-upload__zone--error {
      border-color: rgba(220, 53, 69, 0.5);
    }

    .avatar-upload__content {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 0.5rem;
    }

    .avatar-upload__icon {
      width: 48px;
      height: 48px;
      color: var(--mantis-neon);
      margin-bottom: 0.5rem;
    }

    .avatar-upload__text {
      margin: 0;
      font-size: var(--mantis-fs-lg);
      color: var(--cui-body-color);
    }

    .avatar-upload__text strong {
      color: var(--mantis-neon);
    }

    .avatar-upload__hint {
      margin: 0;
      font-size: var(--mantis-fs-body);
      color: var(--cui-secondary-color);
    }

    .avatar-upload__input {
      display: none;
    }

    .avatar-upload__spinner {
      display: flex;
      flex-direction: column;
      align-items: center;
      color: var(--mantis-neon);
    }

    .text-mantis {
      color: var(--mantis-neon) !important;
    }

    .alert {
      display: flex;
      align-items: center;
    }

    .alert svg {
      flex-shrink: 0;
    }
  `]
})
export class AvatarUploadComponent {
  private readonly authService = inject(AuthService);

  @Output() uploaded = new EventEmitter<void>();

  readonly isDragging = signal(false);
  readonly isUploading = signal(false);
  readonly error = signal<string | null>(null);
  readonly success = signal(false);

  // File validation constants
  private readonly MAX_FILE_SIZE = 5 * 1024 * 1024; // 5MB
  private readonly ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp'];

  /**
   * Handle drag over event
   */
  onDragOver(event: DragEvent): void {
    event.preventDefault();
    event.stopPropagation();
    this.isDragging.set(true);
  }

  /**
   * Handle drag leave event
   */
  onDragLeave(event: DragEvent): void {
    event.preventDefault();
    event.stopPropagation();
    this.isDragging.set(false);
  }

  /**
   * Handle drop event
   */
  onDrop(event: DragEvent): void {
    event.preventDefault();
    event.stopPropagation();
    this.isDragging.set(false);

    const files = event.dataTransfer?.files;
    if (files && files.length > 0) {
      this.processFile(files[0]);
    }
  }

  /**
   * Handle file input change
   */
  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (input.files && input.files.length > 0) {
      this.processFile(input.files[0]);
    }
  }

  /**
   * Process and upload file
   */
  private processFile(file: File): void {
    // Reset states
    this.error.set(null);
    this.success.set(false);

    // Validate file type
    if (!this.ALLOWED_TYPES.includes(file.type)) {
      this.error.set('Tipo di file non supportato. Usa JPG, PNG, GIF o WEBP.');
      return;
    }

    // Validate file size
    if (file.size > this.MAX_FILE_SIZE) {
      this.error.set('Il file è troppo grande. Dimensione massima: 5MB.');
      return;
    }

    // Upload file
    this.isUploading.set(true);
    this.authService.uploadAvatar(file).subscribe({
      next: () => {
        this.isUploading.set(false);
        this.success.set(true);
        this.uploaded.emit();

        // Clear success message after 3 seconds
        setTimeout(() => {
          this.success.set(false);
        }, 3000);
      },
      error: (error) => {
        this.isUploading.set(false);
        const errorMessage = error.error?.detail || error.message || 'Errore durante il caricamento dell\'avatar';
        this.error.set(errorMessage);
      }
    });
  }
}
