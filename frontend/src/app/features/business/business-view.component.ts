import { Component, OnInit, computed, effect, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

import { FleetService } from '../../shared/fleet.service';
import { SiteSummary } from '../../shared/ops.models';
import { SiteSelectionService } from '../../shared/site-selection.service';
import { SiteTopologyTileComponent, TileFilters } from './site-topology-tile.component';

// Business view (USV O&M Manual section 4): every site of one business on one
// scrolling page. The operator ticks which sites appear; one topology tile per
// ticked site, two columns. Shared filters apply to all tiles; a tile with no
// match shows empty rather than disappearing. Tick state, filters and scroll
// survive opening a site and coming back.
@Component({
  selector: 'app-business-view',
  standalone: true,
  imports: [FormsModule, SiteTopologyTileComponent],
  templateUrl: './business-view.component.html',
  styleUrl: './business-view.component.scss',
})
export class BusinessViewComponent implements OnInit {
  private readonly fleet = inject(FleetService);
  private readonly router = inject(Router);
  readonly selection = inject(SiteSelectionService);

  readonly summaries = signal<SiteSummary[]>([]);
  readonly filters = signal<TileFilters>(this.readFilters());

  readonly tiles = computed(() => {
    const ticked = new Set(this.selection.tickedIds());
    return this.summaries().filter((s) => ticked.has(s.site_id));
  });

  constructor() {
    // reload counts whenever the business or the ticked sites change
    effect(() => {
      const ids = this.selection.sitesInBusiness().map((s) => s.site_id);
      if (ids.length) {
        this.fleet.siteSummary(ids).subscribe((rows) => this.summaries.set(rows));
      } else {
        this.summaries.set([]);
      }
    });
  }

  ngOnInit(): void {
    this.selection.load();
  }

  setFilter(patch: Partial<TileFilters>): void {
    this.filters.set({ ...this.filters(), ...patch });
    try {
      sessionStorage.setItem('usv.businessFilters', JSON.stringify(this.filters()));
    } catch {
      // not remembered
    }
  }

  openSite(siteId: string): void {
    this.router.navigate(['/business/site', siteId]);
  }

  stateOf(siteId: string): string {
    return this.summaries().find((s) => s.site_id === siteId)?.state ?? '';
  }

  private readFilters(): TileFilters {
    try {
      const raw = sessionStorage.getItem('usv.businessFilters');
      if (raw) {
        return JSON.parse(raw);
      }
    } catch {
      // ignore
    }
    return { severity: '', assetType: '', zone: '', onlyWithAlerts: false };
  }
}
