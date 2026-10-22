import { Component, OnInit, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { catchError, of } from 'rxjs';

import { AuthService } from '../core/auth/auth.service';

const PLATFORM_ADMIN_ROLE = 'usv_platform_admin';

@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './shell.component.html',
  styleUrl: './shell.component.scss',
})
export class ShellComponent implements OnInit {
  private readonly authService = inject(AuthService);

  readonly currentUser = this.authService.currentUser;

  get isPlatformAdmin(): boolean {
    return this.currentUser()?.role === PLATFORM_ADMIN_ROLE;
  }

  get isCustomerAdmin(): boolean {
    return this.currentUser()?.role === 'usv_customer_admin';
  }

  ngOnInit(): void {
    // Re-validates the stored token against the backend. If it's been
    // tampered with, expired, or the user was deactivated server-side,
    // auth.interceptor's 401 handling clears the session and redirects to
    // /login — this just gives that a real request to catch on.
    this.authService
      .fetchCurrentUser()
      .pipe(catchError(() => of(null)))
      .subscribe();
  }

  logout(): void {
    this.authService.logout();
  }
}
