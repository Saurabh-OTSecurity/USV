import { Injectable, computed, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { Observable, map, tap, catchError, of } from 'rxjs';

import { API_BASE_URL } from '../config';

export interface CurrentUser {
  user_id: string;
  username: string;
  role: string;
  display_name: string | null;
  site_id: string | null;
}

interface LoginResponse {
  token: string;
  user: CurrentUser;
}

// sessionStorage, not localStorage: the token is cleared automatically when
// the tab/browser closes, which limits how long a stolen or leaked token
// stays usable from that storage. Tradeoff: the session does not persist
// across tabs or after closing the browser, so users must log in again per
// tab/session. See README.md ("Token storage") for the full rationale.
const TOKEN_KEY = 'usv.auth.token';
const USER_KEY = 'usv.auth.user';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);

  private readonly currentUserSignal = signal<CurrentUser | null>(this.readStoredUser());
  readonly currentUser = this.currentUserSignal.asReadonly();
  readonly isAuthenticated = computed(() => this.currentUserSignal() !== null && this.token !== null);

  get token(): string | null {
    return sessionStorage.getItem(TOKEN_KEY);
  }

  login(username: string, password: string): Observable<CurrentUser> {
    return this.http
      .post<LoginResponse>(`${API_BASE_URL}/api/v1/auth/login`, { username, password })
      .pipe(
        tap((response) => this.storeSession(response.token, response.user)),
        map((response) => response.user)
      );
  }

  // Re-validates the current token against the backend. Used by the shell
  // on load so a stale/expired/tampered token gets caught by a real
  // request (and cleared via auth.interceptor's 401 handling) rather than
  // silently trusting whatever is left in sessionStorage.
  fetchCurrentUser(): Observable<CurrentUser> {
    return this.http.get<CurrentUser>(`${API_BASE_URL}/api/v1/auth/me`).pipe(
      tap((user) => {
        sessionStorage.setItem(USER_KEY, JSON.stringify(user));
        this.currentUserSignal.set(user);
      })
    );
  }

  logout(): void {
    // Backend logout is client-side token discard only (no server-side
    // revocation in Phase 0 — see backend/ARCHITECTURE.md). We still call
    // it for audit-trail symmetry, but clearing local state does not
    // depend on that request succeeding.
    if (this.token) {
      this.http
        .post(`${API_BASE_URL}/api/v1/auth/logout`, {})
        .pipe(catchError(() => of(null)))
        .subscribe();
    }
    this.clearSession();
    this.router.navigate(['/login']);
  }

  clearSession(): void {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(USER_KEY);
    this.currentUserSignal.set(null);
  }

  private storeSession(token: string, user: CurrentUser): void {
    sessionStorage.setItem(TOKEN_KEY, token);
    sessionStorage.setItem(USER_KEY, JSON.stringify(user));
    this.currentUserSignal.set(user);
  }

  private readStoredUser(): CurrentUser | null {
    const raw = sessionStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as CurrentUser) : null;
  }
}
