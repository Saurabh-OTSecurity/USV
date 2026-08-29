import { Component, OnInit, inject, signal } from '@angular/core';
import { ReactiveFormsModule, FormBuilder, Validators } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';

import { UserService, UserProfile } from '../../shared/user.service';

const ROLES = [
  'usv_platform_admin',
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

  readonly roles = ROLES;

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
}
