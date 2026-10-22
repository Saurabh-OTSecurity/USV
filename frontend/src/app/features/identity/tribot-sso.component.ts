import { Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';

import { IdentityService } from '../../shared/identity.service';

// Where a Tribot's "Sign in with USV" sends people (/sso/tribot?site=<id>).
// They are signed in to USV here (the route requires it), USV vouches for
// them with a short-lived signed assertion, and the browser goes back to the
// site's Tribot, which starts its own session (manual section 10).
@Component({
  selector: 'app-tribot-sso',
  standalone: true,
  imports: [RouterLink],
  template: `
    <h1>Signing in to Tribot…</h1>
    @if (error()) {
      <p class="error-text">{{ error() }}</p>
      <a routerLink="/dashboard">Back to USV</a>
    } @else {
      <p>USV is confirming who you are for this site.</p>
    }
  `,
})
export class TribotSsoComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly identity = inject(IdentityService);
  readonly error = signal<string | null>(null);

  ngOnInit(): void {
    const site = this.route.snapshot.queryParamMap.get('site');
    if (!site) {
      this.error.set('No site given.');
      return;
    }
    this.identity.tribotAssertion(site).subscribe({
      next: (r) => {
        if (r.redirect_url) {
          window.location.assign(r.redirect_url);
        } else {
          this.error.set('This site has no Tribot address in USV yet; ask your admin to set it.');
        }
      },
      error: (e: HttpErrorResponse) => this.error.set(e.error?.error?.message ?? 'USV refused the sign-in.'),
    });
  }
}
