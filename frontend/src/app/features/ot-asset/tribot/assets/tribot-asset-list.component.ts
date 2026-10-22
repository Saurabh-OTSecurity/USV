import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { TribotService } from '../../../../shared/tribot.service';
import { TribotContextService } from '../../../../shared/tribot-context.service';
import { TribotAsset, TribotFacetValue } from '../../../../shared/tribot.models';
import { riskLevelPillClass } from '../../../../shared/tribot-pill.util';
import {
  ASSET_COLUMN_CATALOG,
  AssetColumn,
  COLUMN_BY_KEY,
  DEFAULT_ASSET_COLUMNS,
  PINNED_COLUMN,
  cellValue,
  isOverridden,
} from '../../../../shared/asset-columns.util';

// Versioned (2026-09-19). The v1 set was written against defaults that were
// missing MAC, zone, protocols and last seen, so a browser holding one would
// keep showing that short set and the fix would look like it had not worked.
// Bumping the key ignores the stale value once; anything the operator chooses
// afterwards persists normally.
const COLUMN_PREF_KEY = 'usv.tribot.assetColumns.v2';

/**
 * Discovery — the Tribot asset inventory.
 *
 * Rebuilt 2026-09-18 on operator feedback. Three things were wrong:
 *
 * 1. **No IP.** The Host/IP column read `hostname || ip`, and Tribot writes the
 *    literal string "Unknown" into `hostname` for an unidentified device rather
 *    than leaving it null -- so every row read "Unknown" and the address was
 *    never shown. IP is now its own pinned first column (gap A-16/DT-16's
 *    sibling on this screen).
 * 2. **Nine columns against Tribot's catalogue of 24.** All of them are now
 *    available through a column picker, persisted per browser.
 * 3. **Filtering only by risk.** Replaced with pick-a-column-then-narrow: the
 *    field list and the distinct values both come from Tribot
 *    (/assets/filterable-fields and /assets/facets), so the picker cannot offer
 *    a field the API would reject, and the value list is the real distinct set
 *    over the whole session rather than whatever happened to be on this page.
 *
 * Filtering is deliberately server-side. A cursor-paginated client holds one
 * page, so filtering locally would silently search 50 of 24,000 assets and look
 * like a broken filter rather than a missing one.
 */
@Component({
  selector: 'app-tribot-asset-list',
  standalone: true,
  imports: [RouterLink, DatePipe, FormsModule],
  templateUrl: './tribot-asset-list.component.html',
})
export class TribotAssetListComponent implements OnInit {
  private readonly tribotService = inject(TribotService);
  readonly ctx = inject(TribotContextService);

  readonly assets = signal<TribotAsset[]>([]);
  readonly loading = signal(true);
  readonly loadingMore = signal(false);
  readonly error = signal<string | null>(null);
  readonly nextCursor = signal<string | null>(null);
  readonly totalCount = signal(0);

  /** Columns Tribot will accept as `filterBy`, fetched not hardcoded. */
  readonly filterableFields = signal<string[]>([]);
  /** Distinct values of the currently picked column. */
  readonly facetValues = signal<TribotFacetValue[]>([]);
  readonly facetLoading = signal(false);

  readonly pinned = PINNED_COLUMN;
  readonly catalog = ASSET_COLUMN_CATALOG;
  readonly riskLevelPillClass = riskLevelPillClass;
  readonly cellValue = cellValue;
  readonly isOverridden = isOverridden;

  /** Chosen columns, in order, excluding the pinned IP. */
  readonly columnKeys = signal<string[]>([...DEFAULT_ASSET_COLUMNS]);
  readonly paletteOpen = signal(false);

  search = '';
  filterBy = '';
  filterValue = '';

  readonly columns = computed<AssetColumn[]>(() =>
    this.columnKeys().map((k) => COLUMN_BY_KEY[k]).filter((c): c is AssetColumn => !!c),
  );

  /** Catalogue entries not currently shown, for the picker. */
  readonly availableColumns = computed<AssetColumn[]>(() => {
    const chosen = new Set(this.columnKeys());
    return this.catalog.filter((c) => !chosen.has(c.key as string));
  });

  /** Only columns Tribot can actually filter on are offered in the picker. */
  readonly filterableColumns = computed<AssetColumn[]>(() => {
    const allowed = new Set(this.filterableFields());
    return [this.pinned, ...this.catalog].filter(
      (c) => !!c.filterField && allowed.has(c.filterField),
    );
  });

  ngOnInit(): void {
    this.restoreColumns();
    this.tribotService.listAssetFilterableFields().subscribe({
      next: (response) => this.filterableFields.set(response.data),
      // A failure here costs the filter picker, not the table.
      error: () => this.filterableFields.set([]),
    });
    this.reload();
  }

  // ── column preferences ──
  // Per browser via localStorage. Tribot persists these server-side per user
  // (GET/PUT /api/users/me/asset-columns); USV has no per-user preference store
  // yet, so this is the honest local stand-in rather than a fake of that.

  private restoreColumns(): void {
    try {
      const stored = localStorage.getItem(COLUMN_PREF_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        if (Array.isArray(parsed) && parsed.length) {
          this.columnKeys.set(parsed.filter((k: string) => !!COLUMN_BY_KEY[k] && k !== 'ip'));
          return;
        }
      }
    } catch {
      // Private browsing, cleared storage, or a corrupt value: fall through to
      // the defaults rather than blanking the table.
    }
    this.columnKeys.set([...DEFAULT_ASSET_COLUMNS]);
  }

  private persistColumns(): void {
    try {
      localStorage.setItem(COLUMN_PREF_KEY, JSON.stringify(this.columnKeys()));
    } catch {
      // Not fatal -- the choice just will not survive a reload.
    }
  }

  addColumn(key: string): void {
    if (!key || this.columnKeys().includes(key)) return;
    this.columnKeys.update((keys) => [...keys, key]);
    this.persistColumns();
  }

  removeColumn(key: string): void {
    this.columnKeys.update((keys) => keys.filter((k) => k !== key));
    this.persistColumns();
  }

  moveColumn(key: string, delta: number): void {
    this.columnKeys.update((keys) => {
      const index = keys.indexOf(key);
      const target = index + delta;
      if (index < 0 || target < 0 || target >= keys.length) return keys;
      const next = [...keys];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
    this.persistColumns();
  }

  resetColumns(): void {
    this.columnKeys.set([...DEFAULT_ASSET_COLUMNS]);
    this.persistColumns();
  }

  togglePalette(): void {
    this.paletteOpen.update((open) => !open);
  }

  // ── filtering ──

  /** Picking a column loads its distinct values and clears the old value. */
  onFilterFieldChange(): void {
    this.filterValue = '';
    this.facetValues.set([]);
    if (!this.filterBy) {
      this.reload();
      return;
    }
    this.facetLoading.set(true);
    this.tribotService.getAssetFacets(this.filterBy, 200).subscribe({
      next: (response) => {
        this.facetValues.set(response.data.values);
        this.facetLoading.set(false);
      },
      error: () => {
        // Without the value list the operator can still type freely.
        this.facetValues.set([]);
        this.facetLoading.set(false);
      },
    });
    this.reload();
  }

  clearFilters(): void {
    this.search = '';
    this.filterBy = '';
    this.filterValue = '';
    this.facetValues.set([]);
    this.reload();
  }

  private params(cursor?: string) {
    return {
      pageSize: 50,
      cursor,
      search: this.search || undefined,
      filterBy: this.filterBy || undefined,
      filterValue: this.filterBy && this.filterValue ? this.filterValue : undefined,
    };
  }

  reload(): void {
    this.loading.set(true);
    this.error.set(null);
    this.tribotService.listAssets(this.params()).subscribe({
      next: (response) => {
        this.assets.set(response.data);
        this.nextCursor.set(response.pagination.nextCursor);
        this.totalCount.set(response.pagination.totalCount);
        this.loading.set(false);
      },
      error: (err) => {
        this.error.set(this.describeError(err));
        this.loading.set(false);
      },
    });
  }

  loadMore(): void {
    const cursor = this.nextCursor();
    if (!cursor) return;
    this.loadingMore.set(true);
    this.tribotService.listAssets(this.params(cursor)).subscribe({
      next: (response) => {
        this.assets.update((current) => [...current, ...response.data]);
        this.nextCursor.set(response.pagination.nextCursor);
        this.totalCount.set(response.pagination.totalCount);
        this.loadingMore.set(false);
      },
      error: (err) => {
        this.error.set(this.describeError(err));
        this.loadingMore.set(false);
      },
    });
  }

  /** Display label for an asset's name cell, never the bare "Unknown". */
  displayName(asset: TribotAsset): string {
    if (asset.hostname && asset.hostname !== 'Unknown') return asset.hostname;
    return asset.ip || asset.assetId;
  }

  private describeError(err: unknown): string {
    const apiError = (err as { error?: { error?: { code?: string; message?: string } } })?.error?.error;
    if (apiError?.code === 'TRIBOT_NOT_CONFIGURED') {
      return 'Tribot is not configured for this USV instance (set TRIBOT_BASE_URL / TRIBOT_API_TOKEN in the backend).';
    }
    return apiError?.message || 'Unable to load asset data from Tribot.';
  }
}
