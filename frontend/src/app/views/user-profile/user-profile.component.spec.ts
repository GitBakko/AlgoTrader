import type { MockedObject } from 'vitest';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, ActivatedRoute } from '@angular/router';
import { of, throwError } from 'rxjs';
import { UserProfileComponent } from './user-profile.component';
import { AuthService } from '../../core/services/auth.service';
import { ConfirmDialogService } from '../../shared/services/confirm-dialog.service';
import { ToastService } from '../../shared/services/toast.service';
import { User } from '../../core/models/auth.models';
import { ApiResponse } from '../../core/models';
import { signal } from '@angular/core';

describe('UserProfileComponent', () => {
  let component: UserProfileComponent;
  let fixture: ComponentFixture<UserProfileComponent>;
  let authServiceSpy: MockedObject<AuthService>;
  let routerSpy: MockedObject<Router>;

  const mockUser: User = {
    id: 1,
    username: 'testuser',
    email: 'test@example.com',
    role_id: 2,
    role_name: 'TRADER',
    is_active: true,
    last_login: '2024-01-01T10:00:00Z',
    permissions: [
      { resource: 'trading', action: 'execute' },
      { resource: 'positions', action: 'read' }
    ]
  };

  const mockUserResponse: ApiResponse<User> = { success: true, data: mockUser };

  beforeEach(async () => {
    const authSpy = {
      getCurrentUser: vi.fn().mockName('AuthService.getCurrentUser'),
      logout: vi.fn().mockName('AuthService.logout'),
      deleteAvatar: vi.fn().mockName('AuthService.deleteAvatar')
    };
    const routerSpyObj = {
      navigate: vi.fn().mockName('Router.navigate')
    };
    const confirmSpy = {
      confirm: vi.fn().mockName('ConfirmDialogService.confirm')
    };
    const toastSpy = {
      success: vi.fn().mockName('ToastService.success'),
      error: vi.fn().mockName('ToastService.error')
    };

    // Create a signal for currentUser
    (authSpy as any).currentUser = signal(mockUser);

    await TestBed.configureTestingModule({
      imports: [UserProfileComponent],
      providers: [
        { provide: AuthService, useValue: authSpy },
        { provide: Router, useValue: routerSpyObj },
        { provide: ConfirmDialogService, useValue: confirmSpy },
        { provide: ToastService, useValue: toastSpy },
        { provide: ActivatedRoute, useValue: { snapshot: { queryParams: {} }, queryParams: of({}) } }
      ]
    }).compileComponents();

    authServiceSpy = TestBed.inject(AuthService) as MockedObject<AuthService>;
    routerSpy = TestBed.inject(Router) as MockedObject<Router>;
    // ngOnInit calls refreshProfile() — spy must return an observable by default.
    authServiceSpy.getCurrentUser.mockReturnValue(of(mockUserResponse));

    fixture = TestBed.createComponent(UserProfileComponent);
    component = fixture.componentInstance;
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should display user information', () => {
    fixture.detectChanges();
    const compiled = fixture.nativeElement;

    expect(component.user()).toEqual(mockUser);
  });

  it('should refresh profile on init', () => {
    authServiceSpy.getCurrentUser.mockReturnValue(of(mockUserResponse));

    component.ngOnInit();

    expect(authServiceSpy.getCurrentUser).toHaveBeenCalled();
  });

  it('should handle refresh profile success', () => {
    authServiceSpy.getCurrentUser.mockReturnValue(of(mockUserResponse));

    component.refreshProfile();

    expect(component.loading()).toBe(false);
    expect(authServiceSpy.getCurrentUser).toHaveBeenCalled();
  });

  it('should handle refresh profile error', () => {
    const mockError = { error: { error: 'Failed to fetch user' } };
    authServiceSpy.getCurrentUser.mockReturnValue(throwError(() => mockError));

    component.refreshProfile();

    expect(component.loading()).toBe(false);
  });

  it('should logout when logout button is clicked', () => {
    component.logout();

    expect(authServiceSpy.logout).toHaveBeenCalled();
  });

  it('should return correct role badge color', () => {
    expect(component.getRoleBadgeColor('VIEWER')).toBe('info');
    expect(component.getRoleBadgeColor('TRADER')).toBe('success');
    expect(component.getRoleBadgeColor('ADMIN')).toBe('danger');
    expect(component.getRoleBadgeColor(undefined)).toBe('secondary');
    expect(component.getRoleBadgeColor('UNKNOWN_ROLE')).toBe('secondary');
  });

  it('should format date correctly', () => {
    const formatted = component.formatDate('2024-01-01T10:00:00Z');
    expect(formatted).toContain('2024');
  });

  it('should handle null date', () => {
    expect(component.formatDate(null)).toBe('Mai');
    expect(component.formatDate(undefined)).toBe('Mai');
  });
});
