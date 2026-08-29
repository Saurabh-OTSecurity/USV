import { Component, OnInit, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { forkJoin } from 'rxjs';

import { SiteService } from '../../shared/site.service';
import { UsvService } from '../../shared/usv.service';
import { IntegrationService } from '../../shared/integration.service';
import { Site, Usv, Integration } from '../../shared/models';
import { StatusBadgeComponent } from '../../shared/status-badge/status-badge.component';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [DatePipe, StatusBadgeComponent],
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.scss',
})
export class DashboardComponent implements OnInit {
  private readonly siteService = inject(SiteService);
  private readonly usvService = inject(UsvService);
  private readonly integrationService = inject(IntegrationService);

  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly sites = signal<Site[]>([]);
  readonly usvs = signal<Usv[]>([]);
  readonly integrations = signal<Integration[]>([]);

  ngOnInit(): void {
    forkJoin({
      sites: this.siteService.list(),
      usvs: this.usvService.list(),
      integrations: this.integrationService.list(),
    }).subscribe({
      next: ({ sites, usvs, integrations }) => {
        this.sites.set(sites);
        this.usvs.set(usvs);
        this.integrations.set(integrations);
        this.loading.set(false);
      },
      error: () => {
        this.error.set('Unable to load dashboard data from the backend.');
        this.loading.set(false);
      },
    });
  }
}
