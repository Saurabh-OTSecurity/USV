import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../core/config';
import { Integration } from './models';

@Injectable({ providedIn: 'root' })
export class IntegrationService {
  private readonly http = inject(HttpClient);

  list(): Observable<Integration[]> {
    return this.http.get<Integration[]>(`${API_BASE_URL}/api/v1/integrations`);
  }

  get(integrationId: string): Observable<Integration> {
    return this.http.get<Integration>(`${API_BASE_URL}/api/v1/integrations/${integrationId}`);
  }
}
