import { Component, inject, signal } from '@angular/core';
import { ReactiveFormsModule, FormBuilder, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';

import { AuthService } from '../../core/auth/auth.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './login.component.html',
  styleUrl: './login.component.scss',
})
export class LoginComponent {
  private readonly fb = inject(FormBuilder);
  private readonly authService = inject(AuthService);
  private readonly router = inject(Router);

  readonly submitting = signal(false);
  readonly errorMessage = signal<string | null>(null);

  readonly form = this.fb.nonNullable.group({
    username: ['', Validators.required],
    password: ['', Validators.required],
    tenantCode: [''],
  });

  submit(): void {
    if (this.form.invalid || this.submitting()) {
      return;
    }

    this.errorMessage.set(null);
    this.submitting.set(true);

    const { username, password, tenantCode } = this.form.getRawValue();

    this.authService.login(username, password, tenantCode.trim() || null).subscribe({
      next: (user) => {
        // Do not keep the raw password in frontend state past this point.
        this.form.controls.password.reset('');
        this.submitting.set(false);
        // issued/reset/expired password: nothing else works until it's changed
        const back = new URLSearchParams(location.search).get('returnUrl');
        this.router.navigateByUrl(user.must_change_password ? '/change-password' : back || '/dashboard');
      },
      error: (err: HttpErrorResponse) => {
        this.form.controls.password.reset('');
        this.submitting.set(false);
        // Backend already returns a generic message that does not reveal
        // whether the username or password was wrong — just surface it.
        this.errorMessage.set(
          err.error?.error?.message ?? 'Unable to sign in. Please try again.'
        );
      },
    });
  }
}
