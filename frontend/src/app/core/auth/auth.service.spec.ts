import { TestBed } from '@angular/core/testing';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideRouter } from '@angular/router';

import { AuthService } from './auth.service';
import { API_BASE_URL } from '../config';

describe('AuthService', () => {
  let service: AuthService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    sessionStorage.clear();

    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });

    service = TestBed.inject(AuthService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
    sessionStorage.clear();
  });

  it('login success stores the token and user, and updates currentUser/isAuthenticated', () => {
    const mockUser = {
      user_id: 'u-1',
      username: 'platform.admin',
      role: 'usv_platform_admin',
      display_name: 'Platform Admin',
      site_id: 's-1',
    };

    let result: unknown;
    service.login('platform.admin', 'DevOnly!PlatformAdmin1').subscribe((user) => (result = user));

    const req = httpMock.expectOne(`${API_BASE_URL}/api/v1/auth/login`);
    expect(req.request.method).toBe('POST');
    req.flush({ token: 'fake-token', user: mockUser });

    expect(result).toEqual(mockUser);
    expect(service.token).toBe('fake-token');
    expect(service.currentUser()).toEqual(mockUser);
    expect(service.isAuthenticated()).toBeTrue();
    expect(sessionStorage.getItem('usv.auth.token')).toBe('fake-token');
  });

  it('login failure does not store a session', () => {
    let errored = false;
    service.login('platform.admin', 'wrong-password').subscribe({
      next: () => fail('expected login to error'),
      error: () => (errored = true),
    });

    const req = httpMock.expectOne(`${API_BASE_URL}/api/v1/auth/login`);
    req.flush(
      { error: { code: 'UNAUTHORIZED', message: 'Invalid username or password' } },
      { status: 401, statusText: 'Unauthorized' }
    );

    expect(errored).toBeTrue();
    expect(service.token).toBeNull();
    expect(service.currentUser()).toBeNull();
    expect(service.isAuthenticated()).toBeFalse();
    expect(sessionStorage.getItem('usv.auth.token')).toBeNull();
  });
});
