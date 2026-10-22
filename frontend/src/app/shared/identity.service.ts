import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../core/config';
import { Approver, BreakGlassRequest, Customer, PendingReset } from './ops.models';

// Passwords, approvals, break-glass, single sign-on, customers (manual sections 10-11).
@Injectable({ providedIn: 'root' })
export class IdentityService {
  private readonly http = inject(HttpClient);
  private readonly base = `${API_BASE_URL}/api/v1`;

  changePassword(current_password: string, new_password: string): Observable<{ message: string }> {
    return this.http.post<{ message: string }>(`${this.base}/auth/change-password`, { current_password, new_password });
  }

  passwordPolicy(): Observable<Record<string, number | null>> {
    return this.http.get<Record<string, number | null>>(`${this.base}/auth/password-policy`);
  }

  // forgot password (no login)
  requestReset(username: string, tenant_code: string | null): Observable<{ message: string; reference: string }> {
    return this.http.post<{ message: string; reference: string }>(`${this.base}/password-resets`, { username, tenant_code });
  }

  resetStatus(reference: string, tenant_code: string | null): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(`${this.base}/password-resets/status`, { reference, tenant_code });
  }

  completeReset(reference: string, new_password: string, tenant_code: string | null): Observable<{ message: string }> {
    return this.http.post<{ message: string }>(`${this.base}/password-resets/complete`, { reference, new_password, tenant_code });
  }

  pendingResets(): Observable<PendingReset[]> {
    return this.http.get<PendingReset[]>(`${this.base}/password-resets/pending`);
  }

  decideReset(requestId: string, decision: 'approve' | 'reject'): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(`${this.base}/password-resets/${requestId}/${decision}`, {});
  }

  // one-time shares
  openShare(token: string, tenant_code: string | null): Observable<{ purpose: string; username: string | null; secret: string }> {
    return this.http.post<{ purpose: string; username: string | null; secret: string }>(
      `${this.base}/secure-shares/${token}/open`, { tenant_code });
  }

  initialPasswordShare(userId: string): Observable<{ share_path: string; share_token: string; expires_at: string; username: string }> {
    return this.http.post<{ share_path: string; share_token: string; expires_at: string; username: string }>(
      `${this.base}/users/${userId}/initial-password-share`, {});
  }

  unlock(userId: string): Observable<unknown> {
    return this.http.post(`${this.base}/users/${userId}/unlock`, {});
  }

  setEnabled(userId: string, enabled: boolean): Observable<unknown> {
    return this.http.post(`${this.base}/users/${userId}/${enabled ? 'enable' : 'disable'}`, {});
  }

  changeRole(userId: string, body: { role: string; site_id: string | null; business_unit_id: string | null }): Observable<unknown> {
    return this.http.put(`${this.base}/users/${userId}/role`, body);
  }

  // approvers
  approvers(): Observable<Approver[]> {
    return this.http.get<Approver[]>(`${this.base}/approvers`);
  }

  addApprover(body: Omit<Approver, 'approver_id'>): Observable<Approver> {
    return this.http.post<Approver>(`${this.base}/approvers`, body);
  }

  removeApprover(approverId: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/approvers/${approverId}`);
  }

  // break-glass
  breakGlassRequests(): Observable<BreakGlassRequest[]> {
    return this.http.get<BreakGlassRequest[]>(`${this.base}/break-glass/requests`);
  }

  requestBreakGlass(siteId: string, reason: string): Observable<BreakGlassRequest> {
    return this.http.post<BreakGlassRequest>(`${this.base}/sites/${siteId}/break-glass/requests`, { reason });
  }

  approveBreakGlass(requestId: string): Observable<BreakGlassRequest> {
    return this.http.post<BreakGlassRequest>(`${this.base}/break-glass/requests/${requestId}/approve`, {});
  }

  openBreakGlass(requestId: string): Observable<{ username: string; password: string; rotates_at: string }> {
    return this.http.post<{ username: string; password: string; rotates_at: string }>(
      `${this.base}/break-glass/requests/${requestId}/open`, {});
  }

  // single sign-on into a site's Tribot
  tribotAssertion(siteId: string): Observable<{ assertion: string; role: string; redirect_url: string | null }> {
    return this.http.post<{ assertion: string; role: string; redirect_url: string | null }>(
      `${this.base}/sso/tribot/assertion`, { site_id: siteId });
  }

  // customers (database per customer)
  customers(): Observable<Customer[]> {
    return this.http.get<Customer[]>(`${this.base}/platform/customers`);
  }

  createCustomer(body: { tenant_code: string; name: string; admin_username: string }): Observable<Customer & {
    admin_username: string;
    admin_one_time_password: string;
  }> {
    return this.http.post<Customer & { admin_username: string; admin_one_time_password: string }>(
      `${this.base}/platform/customers`, body);
  }
}
