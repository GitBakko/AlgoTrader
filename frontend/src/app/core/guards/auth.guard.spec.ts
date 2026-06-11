import type { MockedObject } from 'vitest';
import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { authGuard } from './auth.guard';
import { AuthService } from '../services/auth.service';

describe('authGuard', () => {
  let authServiceSpy: MockedObject<AuthService>;
  let routerSpy: MockedObject<Router>;

  beforeEach(() => {
    const authSpy = {
      isAuthenticated: vi.fn().mockName('AuthService.isAuthenticated')
    };
    const routerSpyObj = {
      navigate: vi.fn().mockName('Router.navigate')
    };

    TestBed.configureTestingModule({
      providers: [
        { provide: AuthService, useValue: authSpy },
        { provide: Router, useValue: routerSpyObj }
      ]
    });

    authServiceSpy = TestBed.inject(AuthService) as MockedObject<AuthService>;
    routerSpy = TestBed.inject(Router) as MockedObject<Router>;
  });

  it('should allow access when user is authenticated', () => {
    authServiceSpy.isAuthenticated.mockReturnValue(true);

    const result = TestBed.runInInjectionContext(() => authGuard({} as any, { url: '/dashboard' } as any));

    expect(result).toBe(true);
    expect(routerSpy.navigate).not.toHaveBeenCalled();
  });

  it('should redirect to login when user is not authenticated', () => {
    authServiceSpy.isAuthenticated.mockReturnValue(false);

    const result = TestBed.runInInjectionContext(() => authGuard({} as any, { url: '/dashboard' } as any));

    expect(result).toBe(false);
    expect(routerSpy.navigate).toHaveBeenCalledWith(['/login'], {
      queryParams: { returnUrl: '/dashboard' }
    });
  });
});
