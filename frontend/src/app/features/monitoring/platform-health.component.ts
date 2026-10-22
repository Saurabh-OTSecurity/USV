import { Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { Subscription, interval, startWith } from 'rxjs';

import { MonitoringService } from '../../shared/monitoring.service';
import { HealthSummary, Notification, UsvAlert } from '../../shared/ops.models';

// Platform health (USV O&M Manual section 7): site counts by state (click a
// state to list those sites), each site's last contact, ingestion delay,
// database, certificate and backup -- plus USV's own alerts (site silent,
// disconnected, token problems, platform health) with acknowledge, and the
// signed-in person's notifications. Refreshes every 30 seconds.
@Component({
  selector: 'app-platform-health',
  standalone: true,
  imports: [DatePipe, RouterLink],
  templateUrl: './platform-health.component.html',
})
export class PlatformHealthComponent implements OnInit, OnDestroy {
  private readonly monitoring = inject(MonitoringService);

  readonly health = signal<HealthSummary | null>(null);
  readonly alerts = signal<UsvAlert[]>([]);
  readonly notifications = signal<Notification[]>([]);
  readonly stateFilter = signal<string | null>(null);
  readonly showEvents = signal(false);
  readonly error = signal<string | null>(null);
  private sub?: Subscription;

  readonly states = ['healthy', 'silent', 'disconnected', 'waiting_first_data'];
  readonly sites = computed(() => {
    const f = this.stateFilter();
    return (this.health()?.sites ?? []).filter((s) => !f || s.state === f);
  });

  ngOnInit(): void {
    this.sub = interval(30000).pipe(startWith(0)).subscribe(() => this.refresh());
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
  }

  refresh(): void {
    this.monitoring.health().subscribe((h) => this.health.set(h));
    this.monitoring
      .alerts({ status: this.showEvents() ? undefined : 'active', includeEvents: this.showEvents(), limit: 300 })
      .subscribe((a) => this.alerts.set(a));
    this.monitoring.notifications(true).subscribe((n) => this.notifications.set(n));
  }

  toggleEvents(): void {
    this.showEvents.set(!this.showEvents());
    this.refresh();
  }

  acknowledge(a: UsvAlert): void {
    this.monitoring.acknowledge(a.usv_alert_id).subscribe({
      next: () => this.refresh(),
      error: (e: HttpErrorResponse) => this.error.set(e.error?.error?.message ?? 'Could not acknowledge.'),
    });
  }

  markRead(n: Notification): void {
    this.monitoring.markRead(n.notification_id).subscribe(() => this.refresh());
  }

  siteCode(siteId: string | null): string {
    return (this.health()?.sites ?? []).find((s) => s.site_id === siteId)?.site_code ?? '';
  }

  severityClass(sev: string): string {
    return sev === 'Critical' ? 'pill pill-red' : sev === 'Warning' ? 'pill pill-amber' : 'pill pill-neutral';
  }
}
