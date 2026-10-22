import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';

import { IdentityService } from '../../shared/identity.service';
import { Customer } from '../../shared/ops.models';

// Customers sharing this USV, one database each (manual section 9 decision).
// Tribastion platform admins only, and only when USV runs in that mode.
@Component({
  selector: 'app-customers',
  standalone: true,
  imports: [FormsModule],
  template: `
    <h1>Customers</h1>
    @if (unavailable()) {
      <p class="notice">{{ unavailable() }}</p>
    } @else {
      <table class="data-table">
        <thead><tr><th>Code</th><th>Name</th><th>Database</th><th>Status</th></tr></thead>
        <tbody>
          @for (c of customers(); track c.tenant_id) {
            <tr><td class="mono">{{ c.tenant_code }}</td><td>{{ c.name }}</td><td class="mono">{{ c.database_name }}</td><td>{{ c.status }}</td></tr>
          } @empty { <tr><td colspan="4">No customers yet.</td></tr> }
        </tbody>
      </table>

      <form class="form-card" (ngSubmit)="create()">
        <h3>Add customer</h3>
        <label>Customer code <input name="code" [(ngModel)]="code" placeholder="ACME" /></label>
        <label>Name <input name="name" [(ngModel)]="name" placeholder="Acme Power Ltd" /></label>
        <label>First customer admin user name <input name="admin" [(ngModel)]="admin" placeholder="acme.admin" /></label>
        <p class="small-note">Creates the customer's own database and its first admin. Takes a few seconds.</p>
        @if (error()) { <p class="error-text">{{ error() }}</p> }
        <button class="btn btn-primary" type="submit" [disabled]="busy()">{{ busy() ? 'Creating…' : 'Add customer' }}</button>
      </form>
      @if (created(); as c) {
        <div class="card">
          <p>{{ c.tenant_code }} is ready. First admin: <span class="mono">{{ c.admin_username }}</span></p>
          <p>One-time password (shown once; hand it over through a separate channel, they change it at first login):</p>
          <p class="mono token-box">{{ c.admin_one_time_password }}</p>
        </div>
      }
    }
  `,
})
export class CustomersComponent implements OnInit {
  private readonly identity = inject(IdentityService);

  code = '';
  name = '';
  admin = '';
  readonly customers = signal<Customer[]>([]);
  readonly created = signal<{ tenant_code: string; admin_username: string; admin_one_time_password: string } | null>(null);
  readonly unavailable = signal<string | null>(null);
  readonly error = signal<string | null>(null);
  readonly busy = signal(false);

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.identity.customers().subscribe({
      next: (c) => this.customers.set(c),
      error: (e: HttpErrorResponse) => this.unavailable.set(e.error?.error?.message ?? 'Not available.'),
    });
  }

  create(): void {
    this.busy.set(true);
    this.error.set(null);
    this.identity.createCustomer({ tenant_code: this.code.trim(), name: this.name.trim(), admin_username: this.admin.trim() })
      .subscribe({
        next: (c) => { this.created.set(c); this.busy.set(false); this.load(); },
        error: (e: HttpErrorResponse) => { this.busy.set(false); this.error.set(e.error?.error?.message ?? 'Could not add.'); },
      });
  }
}
