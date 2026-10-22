import { Component, OnInit, computed, effect, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import { FleetService } from '../../shared/fleet.service';
import {
  CorrelationGroup, FleetAlert, FleetAsset, FleetIncident, FleetRemediation, SiteSummary,
} from '../../shared/ops.models';
import { SiteSelectionService } from '../../shared/site-selection.service';

type Tab = 'summary' | 'alerts' | 'incidents' | 'remediations' | 'assets' | 'related';

const PAGE = 500;
const CLOSED = ['Closed', 'Resolved', 'Suppressed', 'False Positive', 'closed', 'resolved', 'done', 'completed'];

// Aggregated alerts, incidents, remediations and assets across the ticked
// sites (USV O&M Manual section 5): one selection, every page. A counts strip
// on top, a site column on every row (click it to narrow to that site), a
// per-site summary to see which site is worst, and "Related across sites"
// from correlation groups (CVE plus asset type). Lists are paged (500 rows).
@Component({
  selector: 'app-fleet-lists',
  standalone: true,
  imports: [DatePipe, FormsModule, RouterLink],
  templateUrl: './fleet-lists.component.html',
})
export class FleetListsComponent implements OnInit {
  private readonly fleet = inject(FleetService);
  private readonly router = inject(Router);
  readonly selection = inject(SiteSelectionService);

  readonly tab = signal<Tab>('summary');
  readonly offset = signal(0);
  readonly total = signal(0);
  readonly loading = signal(false);
  readonly onlySite = signal<string | null>(null);
  readonly textFilter = signal('');

  readonly summaries = signal<SiteSummary[]>([]);
  readonly alerts = signal<FleetAlert[]>([]);
  readonly incidents = signal<FleetIncident[]>([]);
  readonly remediations = signal<FleetRemediation[]>([]);
  readonly assets = signal<FleetAsset[]>([]);
  readonly related = signal<CorrelationGroup[]>([]);

  readonly siteIds = computed(() => (this.onlySite() ? [this.onlySite()!] : this.selection.tickedIds()));

  readonly strip = computed(() => {
    const rows = this.summaries();
    const sev = { critical: 0, high: 0, medium: 0, low: 0 } as Record<string, number>;
    let assets = 0, incidents = 0, remediations = 0, silent = 0;
    for (const r of rows) {
      for (const [k, v] of Object.entries(r.open_alerts)) {
        sev[k] = (sev[k] ?? 0) + v;
      }
      assets += r.assets; incidents += r.open_incidents; remediations += r.open_remediations; silent += r.silent_assets;
    }
    return { sev, assets, incidents, remediations, silent };
  });

  readonly worstFirst = computed(() => [...this.summaries()].sort(
    (a, b) => (b.open_alerts['critical'] ?? 0) - (a.open_alerts['critical'] ?? 0)
      || (b.open_alerts['high'] ?? 0) - (a.open_alerts['high'] ?? 0)));

  constructor() {
    effect(() => {
      const ids = this.siteIds();
      const tab = this.tab();
      const offset = this.offset();
      this.load(ids, tab, offset);
    });
  }

  ngOnInit(): void {
    this.selection.load();
  }

  show(tab: Tab): void {
    this.offset.set(0);
    this.tab.set(tab);
  }

  narrowTo(siteId: string): void {
    this.offset.set(0);
    this.onlySite.set(siteId);
  }

  clearNarrow(): void {
    this.onlySite.set(null);
  }

  page(delta: number): void {
    this.offset.set(Math.max(0, this.offset() + delta * PAGE));
  }

  isOpen(status: string | null): boolean {
    return !CLOSED.includes(status ?? '');
  }

  matches(...values: (string | null | undefined)[]): boolean {
    const f = this.textFilter().trim().toLowerCase();
    return !f || values.some((v) => (v ?? '').toLowerCase().includes(f));
  }

  openSite(siteId: string): void {
    this.router.navigate(['/business/site', siteId]);
  }

  private load(ids: string[], tab: Tab, offset: number): void {
    if (!ids.length) {
      this.summaries.set([]); this.alerts.set([]); this.incidents.set([]); this.remediations.set([]);
      this.assets.set([]); this.total.set(0);
      return;
    }
    this.fleet.siteSummary(ids).subscribe((rows) => this.summaries.set(rows));
    const q = { siteIds: ids, limit: PAGE, offset };
    this.loading.set(true);
    const done = (total: number) => { this.total.set(total); this.loading.set(false); };
    switch (tab) {
      case 'alerts': this.fleet.alerts(q).subscribe((p) => { this.alerts.set(p.rows); done(p.total); }); break;
      case 'incidents': this.fleet.incidents(q).subscribe((p) => { this.incidents.set(p.rows); done(p.total); }); break;
      case 'remediations': this.fleet.remediations(q).subscribe((p) => { this.remediations.set(p.rows); done(p.total); }); break;
      case 'assets': this.fleet.assets(q).subscribe((p) => { this.assets.set(p.rows); done(p.total); }); break;
      case 'related':
        this.fleet.related(true).subscribe((groups) => {
          const want = new Set(ids);
          this.related.set(groups.filter((g) => g.site_ids.filter((s) => want.has(s)).length >= 2));
          done(this.related().length);
        });
        break;
      default: done(0);
    }
  }
}
