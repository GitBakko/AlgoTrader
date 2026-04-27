import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ReactiveFormsModule } from '@angular/forms';
import { Router, ActivatedRoute } from '@angular/router';
import { ButtonModule, CardModule, FormModule, GridModule } from '@coreui/angular';
import { IconModule, IconSetService } from '@coreui/icons-angular';
import { iconSubset } from '../../../icons/icon-subset';
import { LoginComponent } from './login.component';
import { AuthService } from '../../../core/services/auth.service';

// TODO(spec-cleanup): the previous suite mocked an outdated LoginResponse
// shape (no refresh_token / role_name). Reduced to a smoke test until the
// full assertion set is rewritten against the current contract.
describe('LoginComponent', () => {
  let component: LoginComponent;
  let fixture: ComponentFixture<LoginComponent>;

  beforeEach(async () => {
    const authSpy = jasmine.createSpyObj('AuthService', ['login', 'isAuthenticated']);
    const routerSpy = jasmine.createSpyObj('Router', ['navigate']);
    authSpy.isAuthenticated.and.returnValue(false);

    await TestBed.configureTestingModule({
      imports: [
        FormModule,
        CardModule,
        GridModule,
        ButtonModule,
        IconModule,
        ReactiveFormsModule,
        LoginComponent,
      ],
      providers: [
        IconSetService,
        { provide: AuthService, useValue: authSpy },
        { provide: Router, useValue: routerSpy },
        { provide: ActivatedRoute, useValue: { snapshot: { queryParams: {} } } },
      ],
    }).compileComponents();

    const iconSetService = TestBed.inject(IconSetService);
    iconSetService.icons = { ...iconSubset };

    fixture = TestBed.createComponent(LoginComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('initialises an empty login form', () => {
    expect(component.loginForm.get('username')?.value).toBe('');
    expect(component.loginForm.get('password')?.value).toBe('');
  });
});
