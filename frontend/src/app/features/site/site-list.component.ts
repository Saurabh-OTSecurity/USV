import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { SiteService } from '../../shared/site.service';
import { Site } from '../../shared/models';
import { StatusBadgeComponent } from '../../shared/status-badge/status-badge.component';

@Component({
  selector: 'app-site-list',
  standalone: true,
  imports: [RouterLink, StatusBadgeComponent],
  templateUrl: './site-list.component.html',
})
export class SiteListComponent implements OnInit {
  private readonly siteService = inject(SiteService);

  readonly sites = signal<Site[]>([]);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);

  ngOnInit(): void {
    this.siteService.list().subscribe({
      next: (sites) => {
        this.sites.set(sites);
        this.loading.set(false);
      },
      error: () => {
        this.error.set('Unable to load sites from the backend.');
        this.loading.set(false);
      },
    });
  }
}
