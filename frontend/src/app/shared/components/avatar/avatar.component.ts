import { Component, Input, computed, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { environment } from '../../../../environments/environment';

/**
 * Avatar Component
 * Displays user avatar image or fallback to initials
 * MANTIS AI - User profile pictures with neon green glow
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
      @if (avatarUrl && !imageError()) {
        <img
          [src]="fullAvatarUrl()"
          [alt]="username + ' avatar'"
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
      border-radius: 0.375rem;
      background: linear-gradient(135deg, #161b22 0%, #0d1117 100%);
      border: 2px solid rgba(57, 255, 20, 0.2);
      overflow: hidden;
      font-weight: 600;
      color: #39FF14;
      transition: all 0.2s ease;
      flex-shrink: 0;
    }

    .avatar:hover {
      border-color: rgba(57, 255, 20, 0.4);
    }

    .avatar--glow {
      box-shadow: 0 0 12px rgba(57, 255, 20, 0.3);
    }

    .avatar--glow:hover {
      box-shadow: 0 0 20px rgba(57, 255, 20, 0.5);
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
  @Input() username: string = '';
  @Input() avatarUrl: string | null | undefined = null;
  @Input() size: 'sm' | 'md' | 'lg' | 'xl' = 'md';
  @Input() showGlow: boolean = false;

  // Track image loading errors
  readonly imageError = signal(false);

  // Compute avatar size in pixels
  readonly avatarSize = computed(() => {
    switch (this.size) {
      case 'sm': return 32;
      case 'md': return 48;
      case 'lg': return 64;
      case 'xl': return 96;
      default: return 48;
    }
  });

  // Compute CSS classes
  readonly avatarClasses = computed(() => {
    const classes = ['avatar', `avatar--${this.size}`];
    if (this.showGlow) {
      classes.push('avatar--glow');
    }
    return classes.join(' ');
  });

  // Compute user initials from username
  readonly initials = computed(() => {
    if (!this.username) return '?';

    const words = this.username.trim().split(/\s+/);
    if (words.length === 1) {
      // Single word: take first letter
      return words[0].charAt(0).toUpperCase();
    } else {
      // Multiple words: take first letter of first two words
      return (words[0].charAt(0) + words[1].charAt(0)).toUpperCase();
    }
  });

  // Compute full avatar URL (prepend base URL if relative)
  readonly fullAvatarUrl = computed(() => {
    if (!this.avatarUrl) return '';

    // If URL starts with http/https, use as-is
    if (this.avatarUrl.startsWith('http')) {
      return this.avatarUrl;
    }

    // Otherwise, prepend API base URL
    return `${environment.apiUrl}${this.avatarUrl}`;
  });

  /**
   * Handle image loading error - fallback to initials
   */
  onImageError(): void {
    console.warn('[AvatarComponent] Failed to load avatar image:', this.avatarUrl);
    this.imageError.set(true);
  }
}
