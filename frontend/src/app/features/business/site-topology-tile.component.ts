import {
  AfterViewInit, Component, ElementRef, EventEmitter, Input, OnDestroy, Output, computed, inject, signal,
} from '@angular/core';
import { DatePipe } from '@angular/common';
import { forkJoin } from 'rxjs';

import { FleetService } from '../../shared/fleet.service';
import { FleetAsset, SiteSummary, TopologyLink } from '../../shared/ops.models';

export interface TileFilters {
  severity: string;
  assetType: string;
  zone: string;
  onlyWithAlerts: boolean;
}

interface Node {
  id: string;
  label: string;
  x: number;
  y: number;
  silent: boolean;
  missing: boolean;
  dim: boolean;
}

const W = 520;
const H = 260;

// One site's topology, drawn from the links and assets that site's Tribot
// pushes (USV O&M Manual section 4). Loads only once scrolled into view, so
// a business with hundreds of sites never draws them all at once. Assets are
// laid out in rows by Purdue level; silent assets show as ghost outlines.
@Component({
  selector: 'app-site-topology-tile',
  standalone: true,
  imports: [DatePipe],
  templateUrl: './site-topology-tile.component.html',
  styleUrl: './site-topology-tile.component.scss',
})
export class SiteTopologyTileComponent implements AfterViewInit, OnDestroy {
  private readonly fleet = inject(FleetService);
  private readonly host = inject(ElementRef<HTMLElement>);

  @Input({ required: true }) summary!: SiteSummary;
  @Input() set filters(value: TileFilters) {
    this.filterState.set(value);
  }
  @Output() open = new EventEmitter<string>();

  readonly width = W;
  readonly height = H;
  readonly loaded = signal(false);
  readonly assets = signal<FleetAsset[]>([]);
  readonly links = signal<TopologyLink[]>([]);
  readonly filterState = signal<TileFilters>({ severity: '', assetType: '', zone: '', onlyWithAlerts: false });
  private observer?: IntersectionObserver;

  readonly stale = computed(() => this.summary && (this.summary.state === 'silent' || this.summary.state === 'disconnected'));

  readonly nodes = computed<Node[]>(() => {
    const f = this.filterState();
    const rows = new Map<number, FleetAsset[]>();
    for (const a of this.assets()) {
      const level = a.purdue_level ?? 6;
      rows.set(level, [...(rows.get(level) ?? []), a]);
    }
    const levels = [...rows.keys()].sort((a, b) => a - b);
    const out: Node[] = [];
    levels.forEach((level, r) => {
      const row = rows.get(level)!;
      const y = 24 + (r * (H - 48)) / Math.max(levels.length - 1, 1);
      row.forEach((a, i) => {
        const matches = (!f.assetType || a.device_type === f.assetType) && (!f.zone || a.industrial_zone === f.zone);
        out.push({
          id: a.source_asset_id,
          label: a.name || a.source_asset_id,
          x: 20 + ((i + 0.5) * (W - 40)) / row.length,
          y,
          silent: a.lifecycle_state === 'silent',
          missing: a.lifecycle_state === 'missing_from_tribot',
          dim: !matches,
        });
      });
    });
    return out;
  });

  readonly edges = computed(() => {
    const at = new Map(this.nodes().map((n) => [n.id, n]));
    return this.links()
      .map((l) => ({ a: at.get(l.source_asset_id), b: at.get(l.target_asset_id), protocol: l.protocol }))
      .filter((e) => e.a && e.b) as { a: Node; b: Node; protocol: string | null }[];
  });

  readonly hasMatch = computed(() => {
    const f = this.filterState();
    const alerts = this.summary?.open_alerts ?? {};
    if (f.onlyWithAlerts && !Object.values(alerts).some((n) => n > 0)) {
      return false;
    }
    if (f.severity && !(alerts[f.severity] > 0)) {
      return false;
    }
    return !this.loaded() || this.nodes().some((n) => !n.dim);
  });

  ngAfterViewInit(): void {
    this.observer = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) {
        this.observer?.disconnect();
        this.load();
      }
    }, { rootMargin: '200px' });
    this.observer.observe(this.host.nativeElement);
  }

  ngOnDestroy(): void {
    this.observer?.disconnect();
  }

  severityCount(sev: string): number {
    return this.summary.open_alerts?.[sev] ?? 0;
  }

  private load(): void {
    const q = { siteIds: [this.summary.site_id], limit: 2000 };
    forkJoin({ assets: this.fleet.assets(q), links: this.fleet.topologyLinks(q) }).subscribe(({ assets, links }) => {
      this.assets.set(assets.rows);
      this.links.set(links.rows);
      this.loaded.set(true);
    });
  }
}
