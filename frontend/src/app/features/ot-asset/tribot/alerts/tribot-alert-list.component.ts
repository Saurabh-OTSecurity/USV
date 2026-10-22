import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { TribotService } from '../../../../shared/tribot.service';
import { TribotContextService } from '../../../../shared/tribot-context.service';
import { TribotAlert } from '../../../../shared/tribot.models';
import { alertStatusPillClass, severityPillClass } from '../../../../shared/tribot-pill.util';

@Component({
  selector: 'app-tribot-alert-list',
  standalone: true,
  imports: [RouterLink, DatePipe, FormsModule],
  templateUrl: './tribot-alert-list.component.html',
})
export class TribotAlertListComponent implements OnInit {
  private readonly tribotService = inject(TribotService);
  readonly ctx = inject(TribotContextService);

  readonly alerts = signal<TribotAlert[]>([]);
  readonly loading = signal(true);
  readonly loadingMore = signal(false);
  readonly error = signal<string | null>(null);
  readonly nextCursor = signal<string | null>(null);

  severity = '';
  status = '';
  category = '';

  readonly severityPillClass = severityPillClass;
  readonly alertStatusPillClass = alertStatusPillClass;

  ngOnInit(): void {
    this.reload();
  }

  reload(): void {
    this.loading.set(true);
    this.error.set(null);
    this.tribotService
      .listAlerts({
        pageSize: 50,
        severity: this.severity || undefined,
        status: this.status || undefined,
        category: this.category || undefined,
      })
      .subscribe({
        next: (response) => {
          this.alerts.set(response.data);
          this.nextCursor.set(response.pagination.nextCursor);
          this.loading.set(false);
        },
        error: () => {
          this.error.set('Unable to load alert data from Tribot.');
          this.loading.set(false);
        },
      });
  }

  loadMore(): void {
    const cursor = this.nextCursor();
    if (!cursor) return;
    this.loadingMore.set(true);
    this.tribotService
      .listAlerts({
        pageSize: 50,
        cursor,
        severity: this.severity || undefined,
        status: this.status || undefined,
        category: this.category || undefined,
      })
      .subscribe({
        next: (response) => {
          this.alerts.update((current) => [...current, ...response.data]);
          this.nextCursor.set(response.pagination.nextCursor);
          this.loadingMore.set(false);
        },
        error: () => {
          this.loadingMore.set(false);
        },
      });
  }
}
