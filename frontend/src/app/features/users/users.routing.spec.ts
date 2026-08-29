import { TestBed } from '@angular/core/testing';
import { RouterTestingHarness } from '@angular/router/testing';
import { Router, provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { routes } from '../../app.routes';
import { API_BASE_URL } from '../../core/config';

const ROLES = [
  'usv_site_admin',
  'usv_l2_analyst',
  'usv_l1_operator',
  'usv_auditor',
  'usv_viewer',
];

function storeSession(role: string): void {
  sessionStorage.setItem('usv.auth.token', 'a-token');
  sessionStorage.setItem(
    'usv.auth.user',
    JSON.stringify({ user_id: 'u-1', username: 'x', role, display_name: null, site_id: null })
  );
}

describe('users route (real app.routes.ts config)', () => {
  let httpMock: HttpTestingController;

  beforeEach(() => {
    sessionStorage.clear();
    TestBed.configureTestingModule({
      providers: [provideRouter(routes), provideHttpClient(), provideHttpClientTesting()],
    });
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    sessionStorage.clear();
  });

  ROLES.forEach((role) => {
    it(`is blocked for ${role} (redirects to /dashboard)`, async () => {
      storeSession(role);
      const harness = await RouterTestingHarness.create();
      await harness.navigateByUrl('/users');

      // ShellComponent re-validates the session via /auth/me on load.
      httpMock
        .match(`${API_BASE_URL}/api/v1/auth/me`)
        .forEach((req) => req.flush({ user_id: 'u-1', username: 'x', role, display_name: null, site_id: null }));

      expect(TestBed.inject(Router).url).toBe('/dashboard');
    });
  });

  it('is reachable for usv_platform_admin', async () => {
    storeSession('usv_platform_admin');
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl('/users');

    httpMock
      .match(`${API_BASE_URL}/api/v1/auth/me`)
      .forEach((req) =>
        req.flush({ user_id: 'u-1', username: 'x', role: 'usv_platform_admin', display_name: null, site_id: null })
      );
    httpMock.match(`${API_BASE_URL}/api/v1/users`).forEach((req) => req.flush([]));

    expect(TestBed.inject(Router).url).toBe('/users');
  });
});
