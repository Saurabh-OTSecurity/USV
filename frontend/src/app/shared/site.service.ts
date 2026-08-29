import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../core/config';
import { Site } from './models';

@Injectable({ providedIn: 'root' })
export class SiteService {
  private readonly http = inject(HttpClient);

  list(): Observable<Site[]> {
    return this.http.get<Site[]>(`${API_BASE_URL}/api/v1/site`);
  }

  get(siteId: string): Observable<Site> {
    return this.http.get<Site>(`${API_BASE_URL}/api/v1/site/${siteId}`);
  }
}
