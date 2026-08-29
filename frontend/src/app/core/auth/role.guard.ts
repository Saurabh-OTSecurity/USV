import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import { AuthService } from './auth.service';

// UX convenience only, same as auth.guard.ts. The backend re-enforces the
// exact same role restriction on every request (see /api/v1/users' use of
// require_role(USV_PLATFORM_ADMIN) in Story Points 2-4) — this guard just
// avoids showing an authenticated-but-unauthorized user a dead screen full
// of requests that would all come back 403.
export function roleGuard(allowedRoles: string[]): CanActivateFn {
  return () => {
    const authService = inject(AuthService);
    const router = inject(Router);

    const user = authService.currentUser();
    if (user && allowedRoles.includes(user.role)) {
      return true;
    }

    router.navigate(['/dashboard']);
    return false;
  };
}
