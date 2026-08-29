import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { DatePipe } from '@angular/common';

import { IntegrationService } from '../../shared/integration.service';
import { Integration } from '../../shared/models';
import { StatusBadgeComponent } from '../../shared/status-badge/status-badge.component';

@Component({
  selector: 'app-integrations-list',
  standalone: true,
  imports: [RouterLink, DatePipe, StatusBadgeComponent],
  templateUrl: './integrations-list.component.html',
})
export class IntegrationsListComponent implements OnInit {
  private readonly integrationService = inject(IntegrationService);

  readonly integrations = signal<Integration[]>([]);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);

  ngOnInit(): void {
    this.integrationService.list().subscribe({
      next: (integrations) => {
        this.integrations.set(integrations);
        this.loading.set(false);
      },
      error: () => {
        this.error.set('Unable to load integrations from the backend.');
        this.loading.set(false);
      },
    });
  }
}
