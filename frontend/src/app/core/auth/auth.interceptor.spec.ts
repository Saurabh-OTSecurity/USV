import { TestBed } from '@angular/core/testing';
import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Router, provideRouter } from '@angular/router';

import { authInterceptor } from './auth.interceptor';
import { AuthService } from './auth.service';

describe('authInterceptor', () => {
  let httpClient: HttpClient;
  let httpMock: HttpTestingController;
  let authService: AuthService;
  let router: Router;

  beforeEach(() => {
    sessionStorage.clear();

    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
        provideRouter([]),
      ],
    });

    httpClient = TestBed.inject(HttpClient);
    httpMock = TestBed.inject(HttpTestingController);
    authService = TestBed.inject(AuthService);
    router = TestBed.inject(Router);
  });

  afterEach(() => {
    httpMock.verify();
    sessionStorage.clear();
  });

  it('attaches the Authorization header on an authenticated request', () => {
    sessionStorage.setItem('usv.auth.token', 'my-test-token');

    httpClient.get('http://localhost:8000/api/v1/site').subscribe();

    const req = httpMock.expectOne('http://localhost:8000/api/v1/site');
    expect(req.request.headers.get('Authorization')).toBe('Bearer my-test-token');
    req.flush([]);
  });

  it('clears the session and redirects to /login on a 401 response', () => {
    sessionStorage.setItem('usv.auth.token', 'stale-token');
    sessionStorage.setItem(
      'usv.auth.user',
      JSON.stringify({ user_id: 'u-1', username: 'x', role: 'usv_viewer', display_name: null, site_id: null })
    );
    const clearSessionSpy = spyOn(authService, 'clearSession').and.callThrough();
    const navigateSpy = spyOn(router, 'navigate');

    httpClient.get('http://localhost:8000/api/v1/site').subscribe({
      next: () => fail('expected an error'),
      error: () => {
        expect(clearSessionSpy).toHaveBeenCalled();
        expect(navigateSpy).toHaveBeenCalledWith(['/login']);
        expect(sessionStorage.getItem('usv.auth.token')).toBeNull();
      },
    });

    const req = httpMock.expectOne('http://localhost:8000/api/v1/site');
    req.flush(
      { error: { code: 'UNAUTHORIZED', message: 'Authentication required' } },
      { status: 401, statusText: 'Unauthorized' }
    );
  });
});
