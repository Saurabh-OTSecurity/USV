import { Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { DatePipe } from '@angular/common';

import { IntegrationService } from '../../shared/integration.service';
import { Integration } from '../../shared/models';
import { StatusBadgeComponent } from '../../shared/status-badge/status-badge.component';

@Component({
  selector: 'app-integration-detail',
  standalone: true,
  imports: [RouterLink, DatePipe, StatusBadgeComponent],
  templateUrl: './integration-detail.component.html',
})
export class IntegrationDetailComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly integrationService = inject(IntegrationService);

  readonly integration = signal<Integration | null>(null);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);

  ngOnInit(): void {
    const integrationId = this.route.snapshot.paramMap.get('id');
    if (!integrationId) {
      this.error.set('No integration id provided.');
      this.loading.set(false);
      return;
    }

    this.integrationService.get(integrationId).subscribe({
      next: (integration) => {
        this.integration.set(integration);
        this.loading.set(false);
      },
      error: () => {
        this.error.set('Integration not found.');
        this.loading.set(false);
      },
    });
  }
}
