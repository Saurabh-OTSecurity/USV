import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../core/config';
import { CurrentUser } from '../core/auth/auth.service';

export type UserProfile = CurrentUser;

export interface UserCreateRequest {
  username: string;
  password: string;
  role: string;
  display_name: string | null;
  site_id: string | null;
  business_unit_id?: string | null;
}

@Injectable({ providedIn: 'root' })
export class UserService {
  private readonly http = inject(HttpClient);

  list(): Observable<UserProfile[]> {
    return this.http.get<UserProfile[]>(`${API_BASE_URL}/api/v1/users`);
  }

  create(payload: UserCreateRequest): Observable<UserProfile> {
    return this.http.post<UserProfile>(`${API_BASE_URL}/api/v1/users`, payload);
  }
}
