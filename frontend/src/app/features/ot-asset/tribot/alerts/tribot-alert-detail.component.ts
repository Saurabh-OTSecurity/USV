import { Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { DatePipe, JsonPipe } from '@angular/common';

import { TribotService } from '../../../../shared/tribot.service';
import { TribotContextService } from '../../../../shared/tribot-context.service';
import { TribotAlert } from '../../../../shared/tribot.models';
import { alertStatusPillClass, severityPillClass } from '../../../../shared/tribot-pill.util';

@Component({
  selector: 'app-tribot-alert-detail',
  standalone: true,
  imports: [RouterLink, DatePipe, JsonPipe],
  templateUrl: './tribot-alert-detail.component.html',
})
export class TribotAlertDetailComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly tribotService = inject(TribotService);
  readonly ctx = inject(TribotContextService);

  readonly alert = signal<TribotAlert | null>(null);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);

  readonly severityPillClass = severityPillClass;
  readonly alertStatusPillClass = alertStatusPillClass;

  ngOnInit(): void {
    const alertId = this.route.snapshot.paramMap.get('id');
    if (!alertId) {
      this.error.set('No alert id provided.');
      this.loading.set(false);
      return;
    }

    this.tribotService.getAlert(alertId).subscribe({
      next: (response) => {
        this.alert.set(response.data);
        this.loading.set(false);
      },
      error: () => {
        this.error.set('Alert not found in Tribot, or Tribot is unreachable.');
        this.loading.set(false);
      },
    });
  }
}
