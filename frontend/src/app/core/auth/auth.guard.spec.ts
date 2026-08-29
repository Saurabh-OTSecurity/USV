import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';

import { authGuard } from './auth.guard';

describe('authGuard', () => {
  let router: Router;

  beforeEach(() => {
    sessionStorage.clear();

    TestBed.configureTestingModule({
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    });

    router = TestBed.inject(Router);
  });

  afterEach(() => {
    sessionStorage.clear();
  });

  it('redirects an unauthenticated navigation attempt to /login', () => {
    const navigateSpy = spyOn(router, 'navigate');

    const result = TestBed.runInInjectionContext(() => authGuard({} as any, {} as any));

    expect(result).toBeFalse();
    expect(navigateSpy).toHaveBeenCalledWith(['/login']);
  });

  it('allows navigation through when a session exists', () => {
    sessionStorage.setItem('usv.auth.token', 'a-token');
    sessionStorage.setItem(
      'usv.auth.user',
      JSON.stringify({ user_id: 'u-1', username: 'x', role: 'usv_viewer', display_name: null, site_id: null })
    );
    const navigateSpy = spyOn(router, 'navigate');

    const result = TestBed.runInInjectionContext(() => authGuard({} as any, {} as any));

    expect(result).toBeTrue();
    expect(navigateSpy).not.toHaveBeenCalled();
  });
});
