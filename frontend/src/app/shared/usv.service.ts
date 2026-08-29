import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../core/config';
import { Usv } from './models';

@Injectable({ providedIn: 'root' })
export class UsvService {
  private readonly http = inject(HttpClient);

  list(): Observable<Usv[]> {
    return this.http.get<Usv[]>(`${API_BASE_URL}/api/v1/usv`);
  }

  get(usvId: string): Observable<Usv> {
    return this.http.get<Usv>(`${API_BASE_URL}/api/v1/usv/${usvId}`);
  }
}
