import { TestBed } from '@angular/core/testing';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideRouter } from '@angular/router';

import { IntegrationsListComponent } from './integrations-list.component';
import { API_BASE_URL } from '../../core/config';

describe('IntegrationsListComponent', () => {
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [IntegrationsListComponent],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('visually distinguishes fixed-engine entries from pluggable entries', () => {
    const fixture = TestBed.createComponent(IntegrationsListComponent);
    fixture.detectChanges();

    httpMock.expectOne(`${API_BASE_URL}/api/v1/integrations`).flush([
      { integration_id: 'i-1', site_id: 's-1', integration_type: 'siem', name: 'Wazuh Manager', provider: 'wazuh', version: null, status: 'configured', is_fixed_engine: true, last_success_at: null, last_error_at: null },
      { integration_id: 'i-2', site_id: 's-1', integration_type: 'asset_source', name: 'Tribot', provider: 'tribot', version: null, status: 'configured', is_fixed_engine: false, last_success_at: null, last_error_at: null },
    ]);

    fixture.detectChanges();

    const el: HTMLElement = fixture.nativeElement;
    const badges = Array.from(el.querySelectorAll('.engine-badge')) as HTMLElement[];
    expect(badges.length).toBe(2);

    const wazuhRow = Array.from(el.querySelectorAll('tbody tr')).find((tr) => tr.textContent?.includes('Wazuh Manager'))!;
    const tribotRow = Array.from(el.querySelectorAll('tbody tr')).find((tr) => tr.textContent?.includes('Tribot'))!;

    expect(wazuhRow.querySelector('.engine-badge')?.classList).toContain('engine-badge--fixed');
    expect(wazuhRow.querySelector('.engine-badge')?.textContent?.trim()).toBe('Fixed engine');

    expect(tribotRow.querySelector('.engine-badge')?.classList).toContain('engine-badge--pluggable');
    expect(tribotRow.querySelector('.engine-badge')?.textContent?.trim()).toBe('Pluggable');
  });
});
