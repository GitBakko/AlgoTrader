import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ReactiveFormsModule } from '@angular/forms';
import { Router, ActivatedRoute } from '@angular/router';
import { of, throwError } from 'rxjs';
import { ButtonModule, CardModule, FormModule, GridModule } from '@coreui/angular';
import { LoginComponent } from './login.component';
import { IconModule } from '@coreui/icons-angular';
import { IconSetService } from '@coreui/icons-angular';
import { iconSubset } from '../../../icons/icon-subset';
import { AuthService } from '../../../core/services/auth.service';

describe('LoginComponent', () => {
  let component: LoginComponent;
  let fixture: ComponentFixture<LoginComponent>;
  let iconSetService: IconSetService;
  let authServiceSpy: jasmine.SpyObj<AuthService>;
  let routerSpy: jasmine.SpyObj<Router>;

  beforeEach(async () => {
    const authSpy = jasmine.createSpyObj('AuthService', ['login', 'isAuthenticated']);
    const routerSpyObj = jasmine.createSpyObj('Router', ['navigate']);

    await TestBed.configureTestingModule({
      imports: [FormModule, CardModule, GridModule, ButtonModule, IconModule, ReactiveFormsModule, LoginComponent],
      providers: [
        IconSetService,
        { provide: AuthService, useValue: authSpy },
        { provide: Router, useValue: routerSpyObj },
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: {
              queryParams: {}
            }
          }
        }
      ]
    })
    .compileComponents();

    authServiceSpy = TestBed.inject(AuthService) as jasmine.SpyObj<AuthService>;
    routerSpy = TestBed.inject(Router) as jasmine.SpyObj<Router>;
    authServiceSpy.isAuthenticated.and.returnValue(false);
  });

  beforeEach(() => {
    iconSetService = TestBed.inject(IconSetService);
    iconSetService.icons = { ...iconSubset };

    fixture = TestBed.createComponent(LoginComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should initialize login form with empty values', () => {
    expect(component.loginForm.get('username')?.value).toBe('');
    expect(component.loginForm.get('password')?.value).toBe('');
  });

  it('should validate required fields', () => {
    const usernameControl = component.loginForm.get('username');
    const passwordControl = component.loginForm.get('password');

    expect(usernameControl?.valid).toBe(false);
    expect(passwordControl?.valid).toBe(false);

    usernameControl?.setValue('testuser');
    passwordControl?.setValue('password123');

    expect(usernameControl?.valid).toBe(true);
    expect(passwordControl?.valid).toBe(true);
  });

  it('should call authService.login on valid form submission', () => {
    const mockResponse = {
      access_token: 'test-token',
      token_type: 'Bearer',
      expires_in: 3600,
      user: {
        id: 1,
        username: 'testuser',
        email: 'test@example.com',
        role_id: 2,
        is_active: true,
        last_login: null
      }
    };

    authServiceSpy.login.and.returnValue(of(mockResponse));

    component.loginForm.setValue({
      username: 'testuser',
      password: 'password123',
      rememberMe: false
    });

    component.onSubmit();

    expect(authServiceSpy.login).toHaveBeenCalledWith('testuser', 'password123');
    expect(routerSpy.navigate).toHaveBeenCalledWith(['/dashboard']);
    expect(component.loading()).toBe(false);
  });

  it('should handle login error', () => {
    const mockError = {
      error: { error: 'Invalid credentials' }
    };

    authServiceSpy.login.and.returnValue(throwError(() => mockError));

    component.loginForm.setValue({
      username: 'testuser',
      password: 'wrongpassword',
      rememberMe: false
    });

    component.onSubmit();

    expect(component.loading()).toBe(false);
    expect(component.errorMessage()).toBe('Invalid credentials');
  });

  it('should not submit if form is invalid', () => {
    component.loginForm.setValue({
      username: 'ab', // too short
      password: '123', // too short
      rememberMe: false
    });

    component.onSubmit();

    expect(authServiceSpy.login).not.toHaveBeenCalled();
    expect(component.errorMessage()).toBe('Inserisci username e password validi');
  });
});
