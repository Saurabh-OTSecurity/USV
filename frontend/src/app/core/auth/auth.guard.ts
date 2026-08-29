import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import { AuthService } from './auth.service';

// UX convenience only. The real security boundary is the backend's own
// token/role enforcement (see backend Story Points 2-4) — every protected
// endpoint re-checks the token and role server-side regardless of what
// this guard does. This guard only prevents an unauthenticated user from
// seeing a confusing/broken screen before their requests would fail.
export const authGuard: CanActivateFn = () => {
  const authService = inject(AuthService);
  const router = inject(Router);

  if (authService.isAuthenticated()) {
    return true;
  }

  router.navigate(['/login']);
  return false;
};
