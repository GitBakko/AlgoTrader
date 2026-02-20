import { Component, input, computed, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { environment } from '../../../../environments/environment';

/**
 * Avatar Component
 * Displays user avatar image or fallback to initials
 * MANTIS AI - User profile pictures
 */
@Component({
  selector: 'app-avatar',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div
      [class]="avatarClasses()"
      [style.width.px]="avatarSize()"
      [style.height.px]="avatarSize()"
    >
      @if (avatarUrl() && !imageError()) {
        <img
          [src]="fullAvatarUrl()"
          [alt]="username() + ' avatar'"
          (error)="onImageError()"
          class="avatar__image"
        />
      } @else {
        <span class="avatar__initials">{{ initials() }}</span>
      }
    </div>
  `,
  styles: [`
    .avatar {
      position: relative;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-radius: 50%;
      background: linear-gradient(135deg, var(--mantis-surface-4, #21262d) 0%, var(--mantis-surface-3, #1c2128) 100%);
      border: 2px solid rgba(139, 148, 158, 0.25);
      overflow: hidden;
      font-weight: 600;
      color: var(--mantis-text-secondary, #adbac7);
      transition: all 0.2s ease;
      flex-shrink: 0;
    }

    .avatar:hover {
      border-color: rgba(139, 148, 158, 0.4);
    }

    .avatar--sm {
      font-size: 0.75rem;
    }

    .avatar--md {
      font-size: 1rem;
    }

    .avatar--lg {
      font-size: 1.25rem;
    }

    .avatar--xl {
      font-size: 1.5rem;
    }

    .avatar__image {
      width: 100%;
      height: 100%;
      object-fit: cover;
    }

    .avatar__initials {
      user-select: none;
      text-transform: uppercase;
    }
  `]
})
export class AvatarComponent {
  readonly username = input<string>('');
  readonly avatarUrl = input<string | null | undefined>(null);
  readonly size = input<'sm' | 'md' | 'lg' | 'xl'>('md');

  // Track image loading errors
  readonly imageError = signal(false);

  // Compute avatar size in pixels
  readonly avatarSize = computed(() => {
    switch (this.size()) {
      case 'sm': return 32;
      case 'md': return 48;
      case 'lg': return 64;
      case 'xl': return 96;
      default: return 48;
    }
  });

  // Compute CSS classes
  readonly avatarClasses = computed(() => {
    return `avatar avatar--${this.size()}`;
  });

  // Compute user initials from username
  readonly initials = computed(() => {
    const name = this.username();
    if (!name) return '?';

    const words = name.trim().split(/\s+/);
    if (words.length === 1) {
      return words[0].charAt(0).toUpperCase();
    } else {
      return (words[0].charAt(0) + words[1].charAt(0)).toUpperCase();
    }
  });

  // Compute full avatar URL (prepend base URL if relative)
  readonly fullAvatarUrl = computed(() => {
    const url = this.avatarUrl();
    if (!url) return '';

    if (url.startsWith('http')) {
      return url;
    }

    return `${environment.apiUrl}${url}`;
  });

  /**
   * Handle image loading error - fallback to initials
   */
  onImageError(): void {
    console.warn('[AvatarComponent] Failed to load avatar image:', this.avatarUrl());
    this.imageError.set(true);
  }
}
