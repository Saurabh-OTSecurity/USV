import { Injectable, computed, inject, signal } from '@angular/core';
import { forkJoin } from 'rxjs';

import { SiteService } from './site.service';
import { FleetService } from './fleet.service';
import { Site } from './models';
import { BusinessUnit } from './ops.models';

const STORAGE_KEY = 'usv.siteSelection';

// One site selection shared by the business view and the aggregated lists
// (USV O&M Manual sections 4-5): tick Power sites A, B and C and every page
// shows only those three. Kept for the browser session so the tick state
// survives opening a site and coming back.
@Injectable({ providedIn: 'root' })
export class SiteSelectionService {
  private readonly siteService = inject(SiteService);
  private readonly fleet = inject(FleetService);

  readonly sites = signal<Site[]>([]);
  readonly businessUnits = signal<BusinessUnit[]>([]);
  readonly businessUnitId = signal<string | null>(null);
  readonly ticked = signal<Set<string>>(new Set());
  readonly loaded = signal(false);

  readonly sitesInBusiness = computed(() => {
    const bu = this.businessUnitId();
    return this.sites().filter((s) => !bu || s.business_unit_id === bu);
  });
  readonly tickedSites = computed(() => this.sitesInBusiness().filter((s) => this.ticked().has(s.site_id)));
  readonly tickedIds = computed(() => this.tickedSites().map((s) => s.site_id));

  load(): void {
    if (this.loaded()) {
      return;
    }
    forkJoin({ sites: this.siteService.list(), units: this.fleet.businessUnits() }).subscribe(({ sites, units }) => {
      this.sites.set(sites);
      this.businessUnits.set(units);
      const saved = this.readSaved();
      if (saved && units.some((u) => u.business_unit_id === saved.bu)) {
        this.businessUnitId.set(saved.bu);
        this.ticked.set(new Set(saved.ticked));
        this.loaded.set(true);
      } else {
        this.pickDefaultBusiness(sites, units);
      }
    });
  }

  chooseBusiness(buId: string | null): void {
    this.applyBusiness(buId);
    this.save();
  }

  // With no remembered choice, open on the business that holds the most
  // assets -- not simply the first in the list, which may be an empty one.
  private pickDefaultBusiness(sites: Site[], units: BusinessUnit[]): void {
    const fallback = units.find((u) => sites.some((s) => s.business_unit_id === u.business_unit_id)) ?? units[0];
    const done = (buId: string | null) => {
      this.applyBusiness(buId);
      this.loaded.set(true);
    };
    if (!sites.length) {
      done(fallback?.business_unit_id ?? null);
      return;
    }
    this.fleet.siteSummary(sites.map((s) => s.site_id)).subscribe({
      next: (rows) => {
        const assetsByBu = new Map<string, number>();
        for (const r of rows) {
          assetsByBu.set(r.business_unit_id, (assetsByBu.get(r.business_unit_id) ?? 0) + r.assets);
        }
        const best = [...assetsByBu.entries()].sort((a, b) => b[1] - a[1])[0];
        done(best && best[1] > 0 ? best[0] : fallback?.business_unit_id ?? null);
      },
      error: () => done(fallback?.business_unit_id ?? null),
    });
  }

  private applyBusiness(buId: string | null): void {
    this.businessUnitId.set(buId);
    // a newly chosen business starts with every site ticked
    this.ticked.set(new Set(this.sitesInBusiness().map((s) => s.site_id)));
  }

  toggle(siteId: string): void {
    const next = new Set(this.ticked());
    next.has(siteId) ? next.delete(siteId) : next.add(siteId);
    this.ticked.set(next);
    this.save();
  }

  selectAll(): void {
    this.ticked.set(new Set(this.sitesInBusiness().map((s) => s.site_id)));
    this.save();
  }

  clearAll(): void {
    this.ticked.set(new Set());
    this.save();
  }

  siteName(siteId: string): string {
    const s = this.sites().find((x) => x.site_id === siteId);
    return s ? s.site_code : siteId.slice(0, 8);
  }

  refresh(): void {
    this.loaded.set(false);
    this.load();
  }

  private save(): void {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ bu: this.businessUnitId(), ticked: [...this.ticked()] }));
    } catch {
      // storage unavailable: selection just isn't remembered
    }
  }

  private readSaved(): { bu: string | null; ticked: string[] } | null {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  }
}
