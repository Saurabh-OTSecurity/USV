import { Component, OnInit, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';

import { TribotService } from '../../../../shared/tribot.service';
import { TribotIrBoard, TribotIrCase } from '../../../../shared/tribot.models';
import {
  IR_CASE_STATUSES,
  IR_TIERS,
  irStatusLabel,
  irStatusPillClass,
  irTierPillClass,
  severityPillClass,
} from '../../../../shared/tribot-pill.util';

/**
 * The Case Board (parity gap IR-01).
 *
 * Read-only, and not only because the External Data API is read-only: Tribot's
 * own board is read-only by the same reasoning. A status change has to go
 * through its backend state machine, which enforces per-transition tier
 * minimums and writes the audit row, so cards are deliberately not draggable
 * here either -- dragging one would imply those can be bypassed.
 *
 * The whole board arrives in a single call (gap IR-02). Rebuilding it from the
 * paginated case list would mean paging every open case and aggregating
 * client-side, which is wrong at any real case volume.
 */
@Component({
  selector: 'app-tribot-case-board',
  standalone: true,
  imports: [DatePipe],
  templateUrl: './tribot-case-board.component.html',
})
export class TribotCaseBoardComponent implements OnInit {
  private readonly tribotService = inject(TribotService);

  readonly board = signal<TribotIrBoard | null>(null);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);

  // Column order comes from Tribot's own CASE_STATUSES so USV's board cannot
  // drift from the backend state machine's ordering (gap IR-06).
  readonly statuses = IR_CASE_STATUSES;
  readonly tiers = IR_TIERS;

  readonly irStatusLabel = irStatusLabel;
  readonly irStatusPillClass = irStatusPillClass;
  readonly irTierPillClass = irTierPillClass;
  readonly severityPillClass = severityPillClass;

  ngOnInit(): void {
    this.reload();
  }

  reload(): void {
    this.loading.set(true);
    this.error.set(null);
    this.tribotService.getIrCaseBoard().subscribe({
      next: (response) => {
        this.board.set(response.data);
        this.loading.set(false);
      },
      error: (err) => {
        this.error.set(this.describeError(err));
        this.loading.set(false);
      },
    });
  }

  columnCount(status: string): number {
    return this.board()?.columns.find((c) => c.status === status)?.count ?? 0;
  }

  tierCount(tier: string): number {
    return this.board()?.pendingOn.find((t) => t.tier === tier)?.count ?? 0;
  }

  cardsFor(status: string): TribotIrCase[] {
    return this.board()?.cards?.[status] ?? [];
  }

  private describeError(err: unknown): string {
    const apiError = (err as { error?: { error?: { code?: string; message?: string } } })?.error?.error;
    if (apiError?.code === 'TRIBOT_NOT_CONFIGURED') {
      return 'Tribot is not configured for this USV instance (set TRIBOT_BASE_URL / TRIBOT_API_TOKEN in the backend).';
    }
    return apiError?.message || 'Unable to load the case board from Tribot.';
  }
}
