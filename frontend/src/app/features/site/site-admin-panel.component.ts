import { Component, Input, OnInit, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';

import { FleetService } from '../../shared/fleet.service';
import { IdentityService } from '../../shared/identity.service';
import { MonitoringService } from '../../shared/monitoring.service';
import { Site } from '../../shared/models';
import { Approver, Downtime, IngestionToken, MonitoringLimits } from '../../shared/ops.models';
import { UserProfile, UserService } from '../../shared/user.service';

// Everything an admin does for one site (USV O&M Manual sections 3, 7, 8, 10,
// 11): the Tribot address for single sign-on, ingestion tokens (issued once,
// rotate, revoke), planned downtime, monitoring limits, break-glass, and the
// site's approvers.
@Component({
  selector: 'app-site-admin-panel',
  standalone: true,
  imports: [DatePipe, FormsModule],
  templateUrl: './site-admin-panel.component.html',
})
export class SiteAdminPanelComponent implements OnInit {
  private readonly fleet = inject(FleetService);
  private readonly monitoring = inject(MonitoringService);
  private readonly identity = inject(IdentityService);
  private readonly users = inject(UserService);

  @Input({ required: true }) site!: Site;

  readonly tokens = signal<IngestionToken[]>([]);
  readonly newToken = signal<string | null>(null);
  readonly downtime = signal<Downtime[]>([]);
  readonly limits = signal<MonitoringLimits | null>(null);
  readonly approvers = signal<Approver[]>([]);
  readonly people = signal<UserProfile[]>([]);
  readonly message = signal<string | null>(null);
  readonly error = signal<string | null>(null);

  tribotUrl = '';
  dtStart = '';
  dtEnd = '';
  dtReason = '';
  limitEdit: Record<string, number | null> = {};
  bgReason = '';
  approverUser = '';
  approverBackup = false;

  ngOnInit(): void {
    this.tribotUrl = this.site.tribot_url ?? '';
    this.reload();
  }

  reload(): void {
    const id = this.site.site_id;
    this.fleet.tokens(id).subscribe({ next: (t) => this.tokens.set(t), error: () => undefined });
    this.monitoring.downtime(id).subscribe({ next: (d) => this.downtime.set(d), error: () => undefined });
    this.monitoring.siteLimits(id).subscribe({
      next: (l) => { this.limits.set(l); this.limitEdit = { ...l.configured }; },
      error: () => undefined,
    });
    this.identity.approvers().subscribe({
      next: (a) => this.approvers.set(a.filter((x) => x.level === 'site' && x.scope_id === id)),
      error: () => undefined,
    });
    this.users.list().subscribe({ next: (u) => this.people.set(u), error: () => undefined });
  }

  private ok(text: string): void {
    this.error.set(null);
    this.message.set(text);
    this.reload();
  }

  private fail(e: HttpErrorResponse, fallback: string): void {
    this.error.set(e.error?.error?.message ?? fallback);
  }

  saveTribotUrl(): void {
    this.fleet.setTribotUrl(this.site.site_id, this.tribotUrl.trim() || null).subscribe({
      next: () => this.ok('Tribot address saved.'),
      error: (e) => this.fail(e, 'Could not save.'),
    });
  }

  issueToken(): void {
    this.fleet.issueToken(this.site.site_id).subscribe({
      next: (t) => { this.newToken.set(t.token ?? null); this.ok('New token issued. Update the Tribot, test it, then revoke the old one.'); },
      error: (e) => this.fail(e, 'Could not issue a token.'),
    });
  }

  revoke(t: IngestionToken): void {
    if (confirm('Revoke this token? The site stops pushing at once if its Tribot still uses it.')) {
      this.fleet.revokeToken(this.site.site_id, t.token_id).subscribe({
        next: () => this.ok('Token revoked.'),
        error: (e) => this.fail(e, 'Could not revoke.'),
      });
    }
  }

  addDowntime(): void {
    this.monitoring.addDowntime(this.site.site_id, {
      starts_at: new Date(this.dtStart).toISOString(),
      ends_at: new Date(this.dtEnd).toISOString(),
      reason: this.dtReason.trim(),
    }).subscribe({
      next: () => { this.dtReason = ''; this.ok('Planned downtime added.'); },
      error: (e) => this.fail(e, 'Could not add the window.'),
    });
  }

  removeDowntime(d: Downtime): void {
    this.monitoring.deleteDowntime(this.site.site_id, d.downtime_id).subscribe({
      next: () => this.ok('Window removed.'),
      error: (e) => this.fail(e, 'Could not remove.'),
    });
  }

  saveLimits(): void {
    const body: Record<string, number | null> = {};
    for (const [k, v] of Object.entries(this.limitEdit)) {
      body[k] = v === null || (v as unknown) === '' ? null : Number(v);
    }
    this.monitoring.saveSiteLimits(this.site.site_id, body).subscribe({
      next: () => this.ok('Limits saved.'),
      error: (e) => this.fail(e, 'Could not save the limits.'),
    });
  }

  requestBreakGlass(): void {
    this.identity.requestBreakGlass(this.site.site_id, this.bgReason.trim()).subscribe({
      next: () => { this.bgReason = ''; this.ok('Break-glass requested. It needs a customer-side and a Tribastion approval (see Approvals).'); },
      error: (e) => this.fail(e, 'Could not request.'),
    });
  }

  addApprover(): void {
    this.identity.addApprover({ level: 'site', scope_id: this.site.site_id, user_id: this.approverUser, is_backup: this.approverBackup })
      .subscribe({ next: () => this.ok('Approver added.'), error: (e) => this.fail(e, 'Could not add.') });
  }

  removeApprover(a: Approver): void {
    this.identity.removeApprover(a.approver_id).subscribe({
      next: () => this.ok('Approver removed.'), error: (e) => this.fail(e, 'Could not remove.'),
    });
  }

  personName(userId: string): string {
    return this.people().find((p) => p.user_id === userId)?.username ?? userId.slice(0, 8);
  }

  limitKeys(): string[] {
    return Object.keys(this.limits()?.bounds ?? {});
  }
}
