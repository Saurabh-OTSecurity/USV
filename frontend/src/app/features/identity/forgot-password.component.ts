import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';

import { IdentityService } from '../../shared/identity.service';

// Forgot password (USV O&M Manual section 11). The answer is the same whether
// or not the user exists. The person keeps the reference; their approver
// confirms it's them through a separate channel and approves; the person then
// sets a new password here with the reference, once, within the time limit.
@Component({
  selector: 'app-forgot-password',
  standalone: true,
  imports: [FormsModule, RouterLink],
  templateUrl: './forgot-password.component.html',
  styleUrl: '../login/login.component.scss',
})
export class ForgotPasswordComponent {
  private readonly identity = inject(IdentityService);

  username = '';
  tenantCode = '';
  reference = '';
  newPassword = '';
  repeat = '';

  readonly message = signal<string | null>(null);
  readonly status = signal<string | null>(null);
  readonly error = signal<string | null>(null);
  readonly done = signal(false);

  private code(): string | null {
    return this.tenantCode.trim() || null;
  }

  request(): void {
    this.error.set(null);
    this.identity.requestReset(this.username.trim(), this.code()).subscribe({
      next: (r) => { this.message.set(r.message); this.reference = r.reference; },
      error: () => this.error.set('Could not send the request. Try again.'),
    });
  }

  check(): void {
    this.identity.resetStatus(this.reference.trim(), this.code()).subscribe((r) => this.status.set(r.status));
  }

  complete(): void {
    if (this.newPassword !== this.repeat) {
      this.error.set('The new passwords do not match.');
      return;
    }
    this.error.set(null);
    this.identity.completeReset(this.reference.trim(), this.newPassword, this.code()).subscribe({
      next: (r) => { this.message.set(r.message); this.done.set(true); },
      error: (e: HttpErrorResponse) => this.error.set(e.error?.error?.message ?? 'Could not set the password.'),
    });
  }
}
