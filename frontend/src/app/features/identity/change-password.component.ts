import { Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';

import { AuthService } from '../../core/auth/auth.service';
import { IdentityService } from '../../shared/identity.service';

// Own password change; also where a person lands when an issued or reset
// password must be changed before anything else works (manual section 10).
@Component({
  selector: 'app-change-password',
  standalone: true,
  imports: [ReactiveFormsModule],
  templateUrl: './change-password.component.html',
})
export class ChangePasswordComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly identity = inject(IdentityService);
  private readonly auth = inject(AuthService);

  readonly minLength = signal(14);
  readonly error = signal<string | null>(null);
  readonly done = signal(false);
  readonly forced = this.auth.currentUser()?.must_change_password ?? false;

  readonly form = this.fb.nonNullable.group({
    current: ['', Validators.required],
    next: ['', Validators.required],
    repeat: ['', Validators.required],
  });

  ngOnInit(): void {
    this.identity.passwordPolicy().subscribe({
      next: (p) => this.minLength.set(Number(p['min_length'] ?? 14)),
      error: () => undefined,
    });
  }

  submit(): void {
    const v = this.form.getRawValue();
    if (v.next !== v.repeat) {
      this.error.set('The new passwords do not match.');
      return;
    }
    this.error.set(null);
    this.identity.changePassword(v.current, v.next).subscribe({
      next: () => {
        this.done.set(true);
        // the server ended every session, this one included: sign in again
        setTimeout(() => this.auth.logout(), 2500);
      },
      error: (e: HttpErrorResponse) => this.error.set(e.error?.error?.message ?? 'Could not change the password.'),
    });
  }
}
