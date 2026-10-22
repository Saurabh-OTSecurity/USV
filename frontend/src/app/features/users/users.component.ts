import { Component, OnInit, inject, signal } from '@angular/core';
import { ReactiveFormsModule, FormBuilder, Validators } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';

import { UserService, UserProfile } from '../../shared/user.service';
import { IdentityService } from '../../shared/identity.service';

const ROLES = [
  'usv_platform_admin',
  'usv_customer_admin',
  'usv_bu_admin',
  'usv_site_admin',
  'usv_l2_analyst',
  'usv_l1_operator',
  'usv_auditor',
  'usv_viewer',
];

@Component({
  selector: 'app-users',
  standalone: true,
  imports: [ReactiveFormsModule],
  templateUrl: './users.component.html',
})
export class UsersComponent implements OnInit {
  private readonly userService = inject(UserService);
  private readonly fb = inject(FormBuilder);
  private readonly identity = inject(IdentityService);

  readonly roles = ROLES;
  readonly shareLink = signal<{ username: string; url: string; expires_at: string } | null>(null);

  readonly users = signal<UserProfile[]>([]);
  readonly loading = signal(true);
  readonly loadError = signal<string | null>(null);

  readonly submitting = signal(false);
  readonly formError = signal<string | null>(null);
  readonly successMessage = signal<string | null>(null);

  readonly form = this.fb.nonNullable.group({
    username: ['', Validators.required],
    password: ['', Validators.required],
    role: ['usv_viewer', Validators.required],
    display_name: [''],
    site_id: [''],
    business_unit_id: [''],
  });

  ngOnInit(): void {
    this.loadUsers();
  }

  private loadUsers(): void {
    this.loading.set(true);
    this.userService.list().subscribe({
      next: (users) => {
        this.users.set(users);
        this.loading.set(false);
      },
      error: () => {
        this.loadError.set('Unable to load users from the backend.');
        this.loading.set(false);
      },
    });
  }

  submit(): void {
    if (this.form.invalid || this.submitting()) {
      return;
    }

    this.formError.set(null);
    this.successMessage.set(null);
    this.submitting.set(true);

    const raw = this.form.getRawValue();

    this.userService
      .create({
        username: raw.username,
        password: raw.password,
        role: raw.role,
        display_name: raw.display_name.trim() ? raw.display_name : null,
        site_id: raw.site_id.trim() ? raw.site_id : null,
        ...(raw.business_unit_id.trim() ? { business_unit_id: raw.business_unit_id.trim() } : {}),
      })
      .subscribe({
        next: (user) => {
          this.submitting.set(false);
          this.successMessage.set(`User "${user.username}" created.`);
          this.form.reset({
            username: '',
            password: '',
            role: 'usv_viewer',
            display_name: '',
            site_id: '',
            business_unit_id: '',
          });
          this.loadUsers();
        },
        error: (err: HttpErrorResponse) => {
          this.submitting.set(false);
          // Never keep the raw password in frontend state past a failed attempt.
          this.form.controls.password.reset('');
          this.formError.set(err.error?.error?.message ?? 'Unable to create user.');
        },
      });
  }

  // ── per-person actions (USV O&M Manual sections 10-11) ──

  private act(done: string, call: { subscribe: (o: object) => unknown }): void {
    this.formError.set(null);
    call.subscribe({
      next: () => { this.successMessage.set(done); this.loadUsers(); },
      error: (err: HttpErrorResponse) => this.formError.set(err.error?.error?.message ?? 'That did not work.'),
    });
  }

  unlock(u: UserProfile): void {
    this.act(`${u.username} unlocked.`, this.identity.unlock(u.user_id));
  }

  setEnabled(u: UserProfile, enabled: boolean): void {
    if (!enabled && !confirm(`Disable ${u.username}? Their sessions end now, here and on every Tribot at its next poll.`)) {
      return;
    }
    this.act(`${u.username} ${enabled ? 'enabled' : 'disabled'}.`, this.identity.setEnabled(u.user_id, enabled));
  }

  changeRole(u: UserProfile): void {
    const role = prompt(`New role for ${u.username} (${this.roles.join(', ')}):`, u.role);
    if (!role) {
      return;
    }
    const site = prompt('Site id it applies to (empty for none):', u.site_id ?? '') ?? '';
    const bu = prompt('Business unit id it applies to (empty for none):', u.business_unit_id ?? '') ?? '';
    this.act(`${u.username} is now ${role}.`, this.identity.changeRole(u.user_id, {
      role: role.trim(), site_id: site.trim() || null, business_unit_id: bu.trim() || null,
    }));
  }

  oneTimePassword(u: UserProfile): void {
    this.identity.initialPasswordShare(u.user_id).subscribe({
      next: (r) => this.shareLink.set({ username: r.username, url: `${location.origin}${r.share_path}`, expires_at: r.expires_at }),
      error: (err: HttpErrorResponse) => this.formError.set(err.error?.error?.message ?? 'Could not create the link.'),
    });
  }
}
