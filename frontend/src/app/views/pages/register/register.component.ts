import { Component, inject, signal, computed, ChangeDetectionStrategy } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { FormBuilder, FormGroup, Validators, ReactiveFormsModule, AbstractControl, ValidationErrors } from '@angular/forms';
import { IconDirective } from '@coreui/icons-angular';
import {
  FormControlDirective,
  InputGroupComponent,
  InputGroupTextDirective
} from '@coreui/angular';
import { AuthService } from '../../../core/services/auth.service';
import { UserRole } from '../../../core/models/auth.models';
import { CommonModule } from '@angular/common';

/**
 * Register Component
 * MANTIS AI - User registration with role selection
 */
@Component({
  selector: 'app-register',
  templateUrl: './register.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    RouterLink,
    InputGroupComponent,
    InputGroupTextDirective,
    IconDirective,
    FormControlDirective
  ]
})
export class RegisterComponent {
  private readonly authService = inject(AuthService);
  private readonly router = inject(Router);
  private readonly fb = inject(FormBuilder);

  readonly registerForm: FormGroup;
  readonly loading = signal(false);
  readonly errorMessage = signal<string | null>(null);
  readonly successMessage = signal<string | null>(null);

  readonly roles = [
    { value: 'VIEWER', name: 'Viewer', description: 'Visualizzazione dati (sola lettura)' },
    { value: 'TRADER', name: 'Trader', description: 'Trading + visualizzazione' },
    { value: 'ADMIN', name: 'Admin', description: 'Accesso completo' }
  ];

  // Password strength computed signals
  readonly passwordStrength = computed(() => {
    const password = this.passwordControl?.value || '';
    if (password.length === 0) return null;

    const hasNumber = /[0-9]/.test(password);
    const hasUpper = /[A-Z]/.test(password);
    const hasLower = /[a-z]/.test(password);
    const hasSpecial = /[!@#$%^&*(),.?":{}|<>]/.test(password);
    const length = password.length;

    let score = 0;
    if (length >= 6) score++;
    if (length >= 10) score++;
    if (hasNumber) score++;
    if (hasUpper && hasLower) score++;
    if (hasSpecial) score++;

    if (score <= 2) return 'weak';
    if (score <= 3) return 'medium';
    return 'strong';
  });

  readonly passwordStrengthLabel = computed(() => {
    const strength = this.passwordStrength();
    if (!strength) return '';
    return strength === 'weak' ? 'Debole' : strength === 'medium' ? 'Media' : 'Forte';
  });

  readonly passwordStrengthBars = computed(() => {
    const strength = this.passwordStrength();
    if (!strength) return [false, false, false, false];
    if (strength === 'weak') return [true, false, false, false];
    if (strength === 'medium') return [true, true, false, false];
    return [true, true, true, true];
  });

  constructor() {
    // Redirect to dashboard if already logged in
    if (this.authService.isAuthenticated()) {
      this.router.navigate(['/dashboard']);
    }

    this.registerForm = this.fb.group({
      username: ['', [Validators.required, Validators.minLength(3), Validators.maxLength(50)]],
      email: ['', [Validators.required, Validators.email]],
      password: ['', [Validators.required, Validators.minLength(6), this.passwordStrengthValidator]],
      confirmPassword: ['', [Validators.required]],
      role_name: ['VIEWER', [Validators.required]]  // Changed to role_name string
    }, {
      validators: this.passwordMatchValidator
    });
  }

  /**
   * Custom validator for password strength
   */
  private passwordStrengthValidator(control: AbstractControl): ValidationErrors | null {
    const value = control.value;
    if (!value) {
      return null;
    }

    const hasNumber = /[0-9]/.test(value);
    const hasUpper = /[A-Z]/.test(value);
    const hasLower = /[a-z]/.test(value);
    const isValidLength = value.length >= 6;

    const passwordValid = hasNumber && hasUpper && hasLower && isValidLength;

    return !passwordValid ? { passwordStrength: true } : null;
  }

  /**
   * Custom validator to check if passwords match
   */
  private passwordMatchValidator(control: AbstractControl): ValidationErrors | null {
    const password = control.get('password');
    const confirmPassword = control.get('confirmPassword');

    if (!password || !confirmPassword) {
      return null;
    }

    return password.value === confirmPassword.value ? null : { passwordMismatch: true };
  }

  onSubmit(): void {
    if (this.registerForm.invalid) {
      this.errorMessage.set('Compila correttamente tutti i campi');
      this.markFormGroupTouched(this.registerForm);
      return;
    }

    this.loading.set(true);
    this.errorMessage.set(null);
    this.successMessage.set(null);

    const { username, email, password, role_name } = this.registerForm.value;

    this.authService.register(username, email, password, role_name).subscribe({
      next: (response) => {
        this.loading.set(false);
        this.successMessage.set('Registrazione completata! Reindirizzamento al login...');

        // Redirect to login after 2 seconds
        setTimeout(() => {
          this.router.navigate(['/login']);
        }, 2000);
      },
      error: (error) => {
        this.loading.set(false);
        const message = error?.error?.error || error?.message || 'Errore durante la registrazione';
        this.errorMessage.set(message);
      }
    });
  }

  private markFormGroupTouched(formGroup: FormGroup): void {
    Object.keys(formGroup.controls).forEach(key => {
      const control = formGroup.get(key);
      control?.markAsTouched();
    });
  }

  get usernameControl() {
    return this.registerForm.get('username');
  }

  get emailControl() {
    return this.registerForm.get('email');
  }

  get passwordControl() {
    return this.registerForm.get('password');
  }

  get confirmPasswordControl() {
    return this.registerForm.get('confirmPassword');
  }

  get roleControl() {
    return this.registerForm.get('role_name');
  }
}
