import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { forkJoin } from 'rxjs';

import { FleetService } from '../../shared/fleet.service';
import { FleetAsset, Tombstone } from '../../shared/ops.models';
import { TribotContextService } from '../../shared/tribot-context.service';

// A site's asset lifecycle (USV O&M Manual section 6): the safety net --
// assets the site's Tribot no longer lists, for an admin to confirm or keep --
// silent assets, and the decommission history.
@Component({
  selector: 'app-site-lifecycle',
  standalone: true,
  imports: [DatePipe],
  templateUrl: './site-lifecycle.component.html',
})
export class SiteLifecycleComponent implements OnInit {
  private readonly fleet = inject(FleetService);
  private readonly context = inject(TribotContextService);

  readonly assets = signal<FleetAsset[]>([]);
  readonly decommissioned = signal<Tombstone[]>([]);
  readonly message = signal<string | null>(null);
  readonly error = signal<string | null>(null);

  readonly missing = computed(() => this.assets().filter((a) => a.lifecycle_state === 'missing_from_tribot'));
  readonly silent = computed(() => this.assets().filter((a) => a.lifecycle_state === 'silent'));

  ngOnInit(): void {
    this.reload();
  }

  reload(): void {
    const q = { siteIds: [this.context.siteId() ?? ''], limit: 2000 };
    forkJoin({ assets: this.fleet.assets(q), gone: this.fleet.decommissioned({ ...q, limit: 100 }) })
      .subscribe(({ assets, gone }) => {
        this.assets.set(assets.rows);
        this.decommissioned.set(gone.rows);
      });
  }

  confirm(a: FleetAsset): void {
    const reason = prompt(`Confirm ${a.name || a.source_asset_id} is gone. Reason:`);
    if (!reason || reason.trim().length < 3) {
      return;
    }
    this.fleet.confirmMissing(a.asset_id, reason.trim()).subscribe({
      next: () => { this.message.set(`${a.name || a.source_asset_id} removed and recorded.`); this.reload(); },
      error: (e: HttpErrorResponse) => this.error.set(e.error?.error?.message ?? 'Could not confirm.'),
    });
  }

  dismiss(a: FleetAsset): void {
    this.fleet.dismissMissing(a.asset_id).subscribe({
      next: () => { this.message.set(`${a.name || a.source_asset_id} kept.`); this.reload(); },
      error: (e: HttpErrorResponse) => this.error.set(e.error?.error?.message ?? 'Could not dismiss.'),
    });
  }
}
