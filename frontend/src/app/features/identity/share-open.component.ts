import { Component, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';

import { IdentityService } from '../../shared/identity.service';

// A one-time secure share (USV O&M Manual section 10). Revealed only when the
// person presses the button -- so a link preview or scanner can't use it up --
// then destroyed; it never works a second time.
@Component({
  selector: 'app-share-open',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './share-open.component.html',
  styleUrl: '../login/login.component.scss',
})
export class ShareOpenComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly identity = inject(IdentityService);

  readonly token = this.route.snapshot.paramMap.get('token') ?? '';
  readonly tenantCode = this.route.snapshot.queryParamMap.get('customer');
  readonly secret = signal<{ username: string | null; secret: string } | null>(null);
  readonly error = signal<string | null>(null);

  reveal(): void {
    this.identity.openShare(this.token, this.tenantCode).subscribe({
      next: (r) => this.secret.set(r),
      error: (e: HttpErrorResponse) => this.error.set(e.error?.error?.message ?? 'This link is not valid.'),
    });
  }
}
