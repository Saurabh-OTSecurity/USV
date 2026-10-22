import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams, HttpResponse } from '@angular/common/http';
import { Observable, map } from 'rxjs';

import { API_BASE_URL } from '../core/config';
import { Site } from './models';
import {
  BusinessUnit,
  CorrelationGroup,
  FleetAlert,
  FleetAsset,
  FleetIncident,
  FleetRemediation,
  IngestionToken,
  Page,
  SiteSummary,
  Tombstone,
  TopologyLink,
} from './ops.models';

export interface FleetQuery {
  siteIds?: string[];
  businessUnitId?: string;
  limit?: number;
  offset?: number;
  lifecycleState?: string;
}

// Fleet data pushed by every site's Tribot (USV O&M Manual sections 4-6).
// List endpoints are paged; the full count comes back in X-Total-Count.
@Injectable({ providedIn: 'root' })
export class FleetService {
  private readonly http = inject(HttpClient);
  private readonly base = `${API_BASE_URL}/api/v1`;

  private params(q: FleetQuery): HttpParams {
    let p = new HttpParams().set('limit', String(q.limit ?? 500)).set('offset', String(q.offset ?? 0));
    if (q.siteIds?.length) {
      p = p.set('siteIds', q.siteIds.join(','));
    }
    if (q.businessUnitId) {
      p = p.set('businessUnitId', q.businessUnitId);
    }
    if (q.lifecycleState) {
      p = p.set('lifecycleState', q.lifecycleState);
    }
    return p;
  }

  private page<T>(path: string, q: FleetQuery): Observable<Page<T>> {
    return this.http
      .get<T[]>(`${this.base}/fleet/${path}`, { params: this.params(q), observe: 'response' })
      .pipe(map((r: HttpResponse<T[]>) => ({ rows: r.body ?? [], total: Number(r.headers.get('X-Total-Count') ?? 0) })));
  }

  assets(q: FleetQuery): Observable<Page<FleetAsset>> {
    return this.page<FleetAsset>('assets', q);
  }

  alerts(q: FleetQuery): Observable<Page<FleetAlert>> {
    return this.page<FleetAlert>('alerts', q);
  }

  incidents(q: FleetQuery): Observable<Page<FleetIncident>> {
    return this.page<FleetIncident>('incidents', q);
  }

  remediations(q: FleetQuery): Observable<Page<FleetRemediation>> {
    return this.page<FleetRemediation>('remediations', q);
  }

  topologyLinks(q: FleetQuery): Observable<Page<TopologyLink>> {
    return this.page<TopologyLink>('topology-links', q);
  }

  decommissioned(q: FleetQuery): Observable<Page<Tombstone>> {
    return this.page<Tombstone>('decommissioned-assets', q);
  }

  siteSummary(siteIds: string[]): Observable<SiteSummary[]> {
    return this.http.get<SiteSummary[]>(`${this.base}/fleet/site-summary`, {
      params: new HttpParams().set('siteIds', siteIds.join(',')),
    });
  }

  related(acrossSitesOnly = true): Observable<CorrelationGroup[]> {
    return this.http.get<CorrelationGroup[]>(`${this.base}/fleet/correlation-groups`, {
      params: new HttpParams().set('acrossSitesOnly', String(acrossSitesOnly)),
    });
  }

  confirmMissing(assetId: string, reason: string): Observable<Tombstone> {
    return this.http.post<Tombstone>(`${this.base}/fleet/assets/${assetId}/confirm-decommission`, { reason });
  }

  dismissMissing(assetId: string): Observable<FleetAsset> {
    return this.http.post<FleetAsset>(`${this.base}/fleet/assets/${assetId}/dismiss-missing`, {});
  }

  // ── business units, sites, tokens (onboarding, manual section 3) ──

  businessUnits(): Observable<BusinessUnit[]> {
    return this.http.get<BusinessUnit[]>(`${this.base}/business-units`);
  }

  createBusinessUnit(name: string): Observable<BusinessUnit> {
    return this.http.post<BusinessUnit>(`${this.base}/business-units`, { name });
  }

  createSite(body: {
    site_code: string;
    name: string;
    business_unit_id: string;
    criticality: string | null;
    timezone: string | null;
    tribot_url: string | null;
  }): Observable<Site> {
    return this.http.post<Site>(`${this.base}/site`, body);
  }

  setTribotUrl(siteId: string, tribotUrl: string | null): Observable<Site> {
    return this.http.put<Site>(`${this.base}/site/${siteId}/tribot-url`, { tribot_url: tribotUrl });
  }

  tokens(siteId: string): Observable<IngestionToken[]> {
    return this.http.get<IngestionToken[]>(`${this.base}/sites/${siteId}/ingestion-tokens`);
  }

  issueToken(siteId: string): Observable<IngestionToken> {
    return this.http.post<IngestionToken>(`${this.base}/sites/${siteId}/ingestion-tokens`, {});
  }

  revokeToken(siteId: string, tokenId: string): Observable<IngestionToken> {
    return this.http.delete<IngestionToken>(`${this.base}/sites/${siteId}/ingestion-tokens/${tokenId}`);
  }
}
