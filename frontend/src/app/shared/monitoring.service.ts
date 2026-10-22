import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../core/config';
import { Downtime, HealthSummary, MonitoringLimits, Notification, UsvAlert } from './ops.models';

// USV's own alerts, platform health, downtime, limits, notifications (manual section 7).
@Injectable({ providedIn: 'root' })
export class MonitoringService {
  private readonly http = inject(HttpClient);
  private readonly base = `${API_BASE_URL}/api/v1/monitoring`;

  alerts(filter: { status?: string; siteId?: string; includeEvents?: boolean; limit?: number } = {}): Observable<UsvAlert[]> {
    let p = new HttpParams().set('limit', String(filter.limit ?? 200));
    if (filter.status) {
      p = p.set('status', filter.status);
    }
    if (filter.siteId) {
      p = p.set('siteId', filter.siteId);
    }
    if (filter.includeEvents === false) {
      p = p.set('includeEvents', 'false');
    }
    return this.http.get<UsvAlert[]>(`${this.base}/alerts`, { params: p });
  }

  acknowledge(alertId: string): Observable<UsvAlert> {
    return this.http.post<UsvAlert>(`${this.base}/alerts/${alertId}/acknowledge`, {});
  }

  health(): Observable<HealthSummary> {
    return this.http.get<HealthSummary>(`${this.base}/health-summary`);
  }

  downtime(siteId: string): Observable<Downtime[]> {
    return this.http.get<Downtime[]>(`${this.base}/sites/${siteId}/downtime`);
  }

  addDowntime(siteId: string, body: { starts_at: string; ends_at: string; reason: string }): Observable<Downtime> {
    return this.http.post<Downtime>(`${this.base}/sites/${siteId}/downtime`, body);
  }

  deleteDowntime(siteId: string, downtimeId: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/sites/${siteId}/downtime/${downtimeId}`);
  }

  siteLimits(siteId: string): Observable<MonitoringLimits> {
    return this.http.get<MonitoringLimits>(`${this.base}/sites/${siteId}/settings`);
  }

  saveSiteLimits(siteId: string, body: Record<string, number | null>): Observable<MonitoringLimits> {
    return this.http.put<MonitoringLimits>(`${this.base}/sites/${siteId}/settings`, body);
  }

  notifications(unreadOnly = false): Observable<Notification[]> {
    return this.http.get<Notification[]>(`${this.base}/notifications`, {
      params: new HttpParams().set('unreadOnly', String(unreadOnly)),
    });
  }

  markRead(notificationId: string): Observable<Notification> {
    return this.http.post<Notification>(`${this.base}/notifications/${notificationId}/read`, {});
  }
}
