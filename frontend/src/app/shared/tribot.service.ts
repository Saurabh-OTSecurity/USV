import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

import { TribotContextService } from './tribot-context.service';
import {
  TribotAlert,
  TribotAlertSummary,
  TribotAsset,
  TribotAssetFacets,
  TribotAssetSummary,
  TribotInstalledPatch,
  TribotInstalledSoftware,
  TribotIrBoard,
  TribotIrCase,
  TribotItemResponse,
  TribotListResponse,
  TribotPurdueLevel,
  TribotTopology,
  TribotTopologyConversation,
  TribotVulnerability,
  TribotVulnerabilitySummary,
  TribotZoneRosterEntry,
} from './tribot.models';


function toHttpParams(params: object): HttpParams {
  let httpParams = new HttpParams();
  // boolean included so `hasExploit=false` / `cisaKev=false` reach Tribot as
  // explicit filters rather than being dropped (gap V-02) -- only
  // undefined/null/'' mean "not set".
  const entries = Object.entries(params) as [string, string | number | boolean | undefined | null][];
  for (const [key, value] of entries) {
    if (value !== undefined && value !== null && value !== '') {
      httpParams = httpParams.set(key, value);
    }
  }
  return httpParams;
}

export interface AssetListParams {
  pageSize?: number;
  cursor?: string;
  sort?: string;
  deviceType?: string;
  riskLevel?: string;
  industrialZone?: string;
  primaryDomain?: string;
  /** Server-side free-text search (gap P-02). */
  search?: string;
  /** Column to narrow on, from listAssetFilterableFields() (gap A-08). */
  filterBy?: string;
  /** Substring matched against that column, case-insensitively. */
  filterValue?: string;
}

export interface AssetChildListParams {
  pageSize?: number;
  cursor?: string;
  sort?: string;
  search?: string;
}

export interface IrCaseListParams {
  pageSize?: number;
  cursor?: string;
  sort?: string;
  status?: string;
  severity?: string;
  pendingTier?: string;
  assetId?: string;
}

export interface VulnerabilityListParams {
  pageSize?: number;
  cursor?: string;
  sort?: string;
  severity?: string;
  assetId?: string;
  cveId?: string;
  hasExploit?: boolean;
  cisaKev?: boolean;
  search?: string;
}

export interface AlertListParams {
  pageSize?: number;
  cursor?: string;
  sort?: string;
  severity?: string;
  status?: string;
  category?: string;
  assetId?: string;
  search?: string;
}

@Injectable({ providedIn: 'root' })
export class TribotService {
  private readonly http = inject(HttpClient);
  private readonly context = inject(TribotContextService);

  // the live Tribot, or the site being viewed (see TribotContextService)
  private get base(): string {
    return this.context.apiBase();
  }

  listAssets(params: AssetListParams = {}): Observable<TribotListResponse<TribotAsset>> {
    return this.http.get<TribotListResponse<TribotAsset>>(`${this.base}/assets`, { params: toHttpParams(params) });
  }

  getAsset(assetId: string): Observable<TribotItemResponse<TribotAsset>> {
    return this.http.get<TribotItemResponse<TribotAsset>>(`${this.base}/assets/${assetId}`);
  }

  listVulnerabilities(params: VulnerabilityListParams = {}): Observable<TribotListResponse<TribotVulnerability>> {
    return this.http.get<TribotListResponse<TribotVulnerability>>(`${this.base}/vulnerabilities`, {
      params: toHttpParams(params),
    });
  }

  listAlerts(params: AlertListParams = {}): Observable<TribotListResponse<TribotAlert>> {
    return this.http.get<TribotListResponse<TribotAlert>>(`${this.base}/alerts`, { params: toHttpParams(params) });
  }

  getAlert(alertId: string): Observable<TribotItemResponse<TribotAlert>> {
    return this.http.get<TribotItemResponse<TribotAlert>>(`${this.base}/alerts/${alertId}`);
  }

  getTopology(pageSize = 200): Observable<TribotItemResponse<TribotTopology>> {
    return this.http.get<TribotItemResponse<TribotTopology>>(`${this.base}/topology`, {
      params: toHttpParams({ pageSize }),
    });
  }

  // ── Whole-session aggregates (gaps A-07, AL-01, V-01) ──
  // Cursor pagination means a page never adds up to the totals Tribot's own
  // summary bars show, so these come from the server, not from summing rows.

  /** Distinct values for one filterable column, with counts (gap A-08). */
  getAssetFacets(field: string, limit?: number): Observable<TribotItemResponse<TribotAssetFacets>> {
    return this.http.get<TribotItemResponse<TribotAssetFacets>>(`${this.base}/assets/facets`, {
      params: toHttpParams({ field, limit }),
    });
  }

  /**
   * Which columns may be filtered on. Fetched rather than hardcoded so the
   * picker cannot offer a field Tribot would reject.
   */
  listAssetFilterableFields(): Observable<TribotItemResponse<string[]>> {
    return this.http.get<TribotItemResponse<string[]>>(`${this.base}/assets/filterable-fields`);
  }

  getAssetSummary(): Observable<TribotItemResponse<TribotAssetSummary>> {
    return this.http.get<TribotItemResponse<TribotAssetSummary>>(`${this.base}/assets/summary`);
  }

  getAlertSummary(): Observable<TribotItemResponse<TribotAlertSummary>> {
    return this.http.get<TribotItemResponse<TribotAlertSummary>>(`${this.base}/alerts/summary`);
  }

  getVulnerabilitySummary(): Observable<TribotItemResponse<TribotVulnerabilitySummary>> {
    return this.http.get<TribotItemResponse<TribotVulnerabilitySummary>>(
      `${this.base}/vulnerabilities/summary`,
    );
  }

  // ── Software & patches per asset (gap A-15) ──

  listAssetSoftware(
    assetId: string,
    params: AssetChildListParams = {},
  ): Observable<TribotListResponse<TribotInstalledSoftware>> {
    return this.http.get<TribotListResponse<TribotInstalledSoftware>>(
      `${this.base}/assets/${assetId}/software`,
      { params: toHttpParams(params) },
    );
  }

  listAssetPatches(
    assetId: string,
    params: AssetChildListParams = {},
  ): Observable<TribotListResponse<TribotInstalledPatch>> {
    return this.http.get<TribotListResponse<TribotInstalledPatch>>(
      `${this.base}/assets/${assetId}/patches`,
      { params: toHttpParams(params) },
    );
  }

  // ── Topology reference data (gaps DT-02, DT-15) ──

  /** Aggregated asset-to-asset conversations (gap DT-17). */
  listTopologyConversations(
    params: { pageSize?: number; cursor?: string } = {},
  ): Observable<TribotListResponse<TribotTopologyConversation>> {
    return this.http.get<TribotListResponse<TribotTopologyConversation>>(
      `${this.base}/topology/conversations`,
      { params: toHttpParams(params) },
    );
  }

  listPurdueLevels(): Observable<TribotListResponse<TribotPurdueLevel>> {
    return this.http.get<TribotListResponse<TribotPurdueLevel>>(`${this.base}/topology/purdue-levels`);
  }

  listTopologyZones(): Observable<TribotListResponse<TribotZoneRosterEntry>> {
    return this.http.get<TribotListResponse<TribotZoneRosterEntry>>(`${this.base}/topology/zones`);
  }

  // ── Incident Response case status, read-only (gaps IR-01, IR-02) ──

  getIrCaseBoard(): Observable<TribotItemResponse<TribotIrBoard>> {
    return this.http.get<TribotItemResponse<TribotIrBoard>>(`${this.base}/ir-cases/board`);
  }

  listIrCases(params: IrCaseListParams = {}): Observable<TribotListResponse<TribotIrCase>> {
    return this.http.get<TribotListResponse<TribotIrCase>>(`${this.base}/ir-cases`, {
      params: toHttpParams(params),
    });
  }

  getIrCase(caseId: string): Observable<TribotItemResponse<TribotIrCase>> {
    return this.http.get<TribotItemResponse<TribotIrCase>>(`${this.base}/ir-cases/${caseId}`);
  }
}
