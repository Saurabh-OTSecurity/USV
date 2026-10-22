import { Component, OnInit, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';

import { AuthService } from '../../core/auth/auth.service';
import { IdentityService } from '../../shared/identity.service';
import { SiteSelectionService } from '../../shared/site-selection.service';
import { BreakGlassRequest, PendingReset } from '../../shared/ops.models';

// Approvals inbox (USV O&M Manual sections 10-11): password resets waiting
// for me, and break-glass requests (one customer-side and one Tribastion
// approval; the requester then sees the password once).
@Component({
  selector: 'app-approvals',
  standalone: true,
  imports: [DatePipe],
  templateUrl: './approvals.component.html',
})
export class ApprovalsComponent implements OnInit {
  private readonly identity = inject(IdentityService);
  private readonly auth = inject(AuthService);
  readonly selection = inject(SiteSelectionService);

  readonly resets = signal<PendingReset[]>([]);
  readonly breakGlass = signal<BreakGlassRequest[]>([]);
  readonly revealed = signal<{ username: string; password: string; rotates_at: string } | null>(null);
  readonly message = signal<string | null>(null);
  readonly error = signal<string | null>(null);
  readonly me = this.auth.currentUser;

  ngOnInit(): void {
    this.selection.load();
    this.refresh();
  }

  refresh(): void {
    this.identity.pendingResets().subscribe((r) => this.resets.set(r));
    this.identity.breakGlassRequests().subscribe({ next: (r) => this.breakGlass.set(r), error: () => undefined });
  }

  decide(r: PendingReset, decision: 'approve' | 'reject'): void {
    if (decision === 'approve' && !confirm(`Did you confirm, by call or message, that ${r.username} really asked for this?`)) {
      return;
    }
    this.identity.decideReset(r.request_id, decision).subscribe({
      next: (res) => { this.message.set(`${r.username}: ${res.status}`); this.refresh(); },
      error: (e: HttpErrorResponse) => this.error.set(e.error?.error?.message ?? 'Could not record the decision.'),
    });
  }

  approveBreakGlass(b: BreakGlassRequest): void {
    this.identity.approveBreakGlass(b.request_id).subscribe({
      next: () => this.refresh(),
      error: (e: HttpErrorResponse) => this.error.set(e.error?.error?.message ?? 'Could not approve.'),
    });
  }

  openBreakGlass(b: BreakGlassRequest): void {
    this.identity.openBreakGlass(b.request_id).subscribe({
      next: (r) => { this.revealed.set(r); this.refresh(); },
      error: (e: HttpErrorResponse) => this.error.set(e.error?.error?.message ?? 'Could not open.'),
    });
  }

  sides(b: BreakGlassRequest): string {
    return b.approvals.map((a) => a.side).join(' + ') || 'none yet';
  }
}
