import { Component, Input, OnInit, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { TribotService } from '../../../../shared/tribot.service';
import {
  TribotAsset,
  TribotInstalledPatch,
  TribotInstalledSoftware,
} from '../../../../shared/tribot.models';

/**
 * The per-asset Software & Patches tab (parity gap A-15).
 *
 * Tribot has published GET /api/v1/assets/{assetId}/software and /patches
 * since its TrustSweep work; USV simply never consumed them, so this whole tab
 * was missing while the data was already on the wire.
 *
 * Filtering and sorting are server-side: a Windows host routinely carries
 * several hundred installed applications, so filtering one loaded page would
 * look like a broken filter rather than a missing one (gap A-17).
 *
 * Read-only. Tribot's own tab can trigger a collection run with one-time WinRM
 * credentials, but that is an admin write on its internal API with no external
 * equivalent (gap A-18) -- so this tab shows what was collected and says when.
 */
type SortDirection = 'asc' | 'desc';

// Tribot's TrustSweep METHOD_LABELS, mirrored so the provenance chip reads the
// same on both products (gap A-16).
const COLLECTION_METHOD_LABELS: Record<string, string> = {
  ad_implicit_scheduled: 'AD-implicit (scheduled)',
  ad_implicit_manual: 'AD-implicit (manual)',
  manual_session: 'Manual credential',
  uncollected: 'Not yet collected',
};

@Component({
  selector: 'app-tribot-asset-software',
  standalone: true,
  imports: [DatePipe, FormsModule],
  templateUrl: './tribot-asset-software.component.html',
})
export class TribotAssetSoftwareComponent implements OnInit {
  @Input({ required: true }) assetId!: string;
  /** Used only for the collection-provenance header (gap A-16). */
  @Input() asset: TribotAsset | null = null;

  private readonly tribotService = inject(TribotService);

  readonly software = signal<TribotInstalledSoftware[]>([]);
  readonly patches = signal<TribotInstalledPatch[]>([]);
  readonly softwareTotal = signal(0);
  readonly patchTotal = signal(0);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);

  softwareSearch = '';
  patchSearch = '';
  softwareSort = 'displayName';
  softwareDir: SortDirection = 'asc';
  patchSort = 'hotfixId';
  patchDir: SortDirection = 'asc';

  ngOnInit(): void {
    this.reload();
  }

  get collectionMethodLabel(): string {
    const method = this.asset?.collectionMethod ?? 'uncollected';
    return COLLECTION_METHOD_LABELS[method] ?? method;
  }

  get collectedAt(): string | null {
    return this.asset?.lastInventoryAt ?? null;
  }

  reload(): void {
    this.loading.set(true);
    this.error.set(null);
    this.loadSoftware();
    this.loadPatches();
  }

  toggleSoftwareSort(key: string): void {
    this.softwareDir = this.softwareSort === key && this.softwareDir === 'asc' ? 'desc' : 'asc';
    this.softwareSort = key;
    this.loadSoftware();
  }

  togglePatchSort(key: string): void {
    this.patchDir = this.patchSort === key && this.patchDir === 'asc' ? 'desc' : 'asc';
    this.patchSort = key;
    this.loadPatches();
  }

  loadSoftware(): void {
    this.tribotService
      .listAssetSoftware(this.assetId, {
        pageSize: 200,
        search: this.softwareSearch || undefined,
        sort: this.softwareDir === 'desc' ? `-${this.softwareSort}` : this.softwareSort,
      })
      .subscribe({
        next: (response) => {
          this.software.set(response.data);
          this.softwareTotal.set(response.pagination.totalCount);
          this.loading.set(false);
        },
        error: (err) => {
          this.error.set(this.describeError(err));
          this.loading.set(false);
        },
      });
  }

  loadPatches(): void {
    this.tribotService
      .listAssetPatches(this.assetId, {
        pageSize: 200,
        search: this.patchSearch || undefined,
        sort: this.patchDir === 'desc' ? `-${this.patchSort}` : this.patchSort,
      })
      .subscribe({
        next: (response) => {
          this.patches.set(response.data);
          this.patchTotal.set(response.pagination.totalCount);
          this.loading.set(false);
        },
        error: (err) => {
          this.error.set(this.describeError(err));
          this.loading.set(false);
        },
      });
  }

  private describeError(err: unknown): string {
    const apiError = (err as { error?: { error?: { code?: string; message?: string } } })?.error?.error;
    if (apiError?.code === 'TRIBOT_NOT_CONFIGURED') {
      return 'Tribot is not configured for this USV instance (set TRIBOT_BASE_URL / TRIBOT_API_TOKEN in the backend).';
    }
    return apiError?.message || 'Unable to load software and patch data from Tribot.';
  }
}
