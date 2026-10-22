import { Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { SiteService } from '../../shared/site.service';
import { Site } from '../../shared/models';
import { StatusBadgeComponent } from '../../shared/status-badge/status-badge.component';
import { SiteAdminPanelComponent } from './site-admin-panel.component';

@Component({
  selector: 'app-site-detail',
  standalone: true,
  imports: [RouterLink, StatusBadgeComponent, SiteAdminPanelComponent],
  templateUrl: './site-detail.component.html',
})
export class SiteDetailComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly siteService = inject(SiteService);

  readonly site = signal<Site | null>(null);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);

  ngOnInit(): void {
    const siteId = this.route.snapshot.paramMap.get('id');
    if (!siteId) {
      this.error.set('No site id provided.');
      this.loading.set(false);
      return;
    }

    this.siteService.get(siteId).subscribe({
      next: (site) => {
        this.site.set(site);
        this.loading.set(false);
      },
      error: () => {
        this.error.set('Site not found.');
        this.loading.set(false);
      },
    });
  }
}
