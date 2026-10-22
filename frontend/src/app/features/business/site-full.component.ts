import { Component, DestroyRef, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { FleetService } from '../../shared/fleet.service';
import { IdentityService } from '../../shared/identity.service';
import { SiteSummary } from '../../shared/ops.models';
import { TribotContextService } from '../../shared/tribot-context.service';

// One site, shown the way Tribot shows it (USV O&M Manual section 4): the
// same Discovery / Topology / Detection & Response / Risk & Compliance / Case
// Board pages as OT Asset > Tribot, fed from what this site's Tribot pushed,
// plus a Lifecycle tab (missing-from-Tribot safety net, decommission
// history). "Open in Tribot" signs the person in there via USV.
@Component({
  selector: 'app-site-full',
  standalone: true,
  imports: [RouterLink, RouterLinkActive, RouterOutlet],
  templateUrl: './site-full.component.html',
  styleUrl: './site-full.component.scss',
})
export class SiteFullComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly fleet = inject(FleetService);
  private readonly identity = inject(IdentityService);
  private readonly context = inject(TribotContextService);

  readonly siteId = signal('');
  readonly summary = signal<SiteSummary | null>(null);
  readonly error = signal<string | null>(null);

  constructor() {
    // Set before the tab pages start, so their first request already goes to
    // this site. The template rebuilds the tab pages per site id.
    this.route.paramMap.pipe(takeUntilDestroyed()).subscribe((params) => {
      const id = params.get('id') ?? '';
      this.siteId.set(id);
      this.context.siteId.set(id);
      this.summary.set(null);
      this.fleet.siteSummary([id]).subscribe((rows) => this.summary.set(rows[0] ?? null));
    });
    inject(DestroyRef).onDestroy(() => {
      if (this.context.siteId() === this.siteId()) {
        this.context.siteId.set(null);
      }
    });
  }

  openInTribot(): void {
    this.error.set(null);
    this.identity.tribotAssertion(this.siteId()).subscribe({
      next: (r) => {
        if (r.redirect_url) {
          window.open(r.redirect_url, '_blank', 'noopener');
        } else {
          this.error.set('This site has no Tribot address yet. Set it on the site page.');
        }
      },
      error: (e: HttpErrorResponse) => this.error.set(e.error?.error?.message ?? 'Sign-in to Tribot was refused.'),
    });
  }
}
