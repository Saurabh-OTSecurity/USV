import { TestBed } from '@angular/core/testing';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideRouter } from '@angular/router';

import { DashboardComponent } from './dashboard.component';
import { API_BASE_URL } from '../../core/config';

describe('DashboardComponent', () => {
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [DashboardComponent],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('renders real site, USV, and integration data fetched from the backend', () => {
    const fixture = TestBed.createComponent(DashboardComponent);
    fixture.detectChanges();

    httpMock.expectOne(`${API_BASE_URL}/api/v1/site`).flush([
      { site_id: 's-1', site_code: 'SITE-001', name: 'Demo Plant', description: null, timezone: null, criticality: null, status: 'active' },
    ]);
    httpMock.expectOne(`${API_BASE_URL}/api/v1/usv`).flush([
      { usv_id: 'u-1', site_id: 's-1', usv_code: 'USV-001', hostname: 'usv-demo-01', installation_id: null, version: '0.1.0', status: 'active', last_heartbeat: null },
    ]);
    httpMock.expectOne(`${API_BASE_URL}/api/v1/integrations`).flush([
      { integration_id: 'i-1', site_id: 's-1', integration_type: 'siem', name: 'Wazuh Manager', provider: 'wazuh', version: null, status: 'configured', is_fixed_engine: true, last_success_at: null, last_error_at: null },
    ]);

    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('SITE-001');
    expect(text).toContain('Demo Plant');
    expect(text).toContain('USV-001');
    expect(text).toContain('0.1.0');
    expect(text).toContain('Wazuh Manager');
    expect(text).toContain('seeded configuration records');
  });
});
