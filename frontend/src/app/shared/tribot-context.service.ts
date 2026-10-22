import { Injectable, signal } from '@angular/core';

import { API_BASE_URL } from '../core/config';

// Which Tribot the OT Asset pages are showing. No site: the one live Tribot
// USV proxies (/api/v1/tribot). A site: that site's pushed data, served by
// USV in the same shapes (/api/v1/fleet/sites/{id}/tribot) -- so the very same
// Discovery / Topology / Detection / Risk / Case Board pages work for every
// onboarded site (USV O&M Manual section 4, "click a site").
@Injectable({ providedIn: 'root' })
export class TribotContextService {
  readonly siteId = signal<string | null>(null);

  apiBase(): string {
    const site = this.siteId();
    return site ? `${API_BASE_URL}/api/v1/fleet/sites/${site}/tribot` : `${API_BASE_URL}/api/v1/tribot`;
  }

  /** Router link inside the current Tribot view, e.g. link('alerts', id). */
  link(...parts: string[]): string[] {
    const site = this.siteId();
    return [site ? `/business/site/${site}` : '/ot-asset/tribot', ...parts];
  }
}
