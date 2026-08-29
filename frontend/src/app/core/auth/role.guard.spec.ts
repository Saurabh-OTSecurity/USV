import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';

import { roleGuard } from './role.guard';

function storeUser(role: string): void {
  sessionStorage.setItem('usv.auth.token', 'a-token');
  sessionStorage.setItem(
    'usv.auth.user',
    JSON.stringify({ user_id: 'u-1', username: 'x', role, display_name: null, site_id: null })
  );
}

describe('roleGuard', () => {
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

  it('blocks a non-platform-admin user from the /users placeholder route', () => {
    storeUser('usv_viewer');
    const navigateSpy = spyOn(router, 'navigate');

    const guard = roleGuard(['usv_platform_admin']);
    const result = TestBed.runInInjectionContext(() => guard({} as any, {} as any));

    expect(result).toBeFalse();
    expect(navigateSpy).toHaveBeenCalledWith(['/dashboard']);
  });

  it('allows a usv_platform_admin user through to the /users placeholder route', () => {
    storeUser('usv_platform_admin');
    const navigateSpy = spyOn(router, 'navigate');

    const guard = roleGuard(['usv_platform_admin']);
    const result = TestBed.runInInjectionContext(() => guard({} as any, {} as any));

    expect(result).toBeTrue();
    expect(navigateSpy).not.toHaveBeenCalled();
  });
});
