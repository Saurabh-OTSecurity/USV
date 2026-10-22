import { Component, OnDestroy, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { Subscription, interval, switchMap } from 'rxjs';

import { API_BASE_URL } from '../../core/config';
import { FleetService } from '../../shared/fleet.service';
import { Site } from '../../shared/models';
import { BusinessUnit } from '../../shared/ops.models';
import { SiteSelectionService } from '../../shared/site-selection.service';

// Add-site wizard (USV O&M Manual section 3): business unit and site, then
// the ingestion token shown once with the Tribot connection details, then a
// waiting state that turns green when the site's first push arrives.
@Component({
  selector: 'app-add-site',
  standalone: true,
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './add-site.component.html',
})
export class AddSiteComponent implements OnInit, OnDestroy {
  private readonly fb = inject(FormBuilder);
  private readonly fleet = inject(FleetService);
  private readonly selection = inject(SiteSelectionService);

  readonly step = signal<1 | 2 | 3>(1);
  readonly units = signal<BusinessUnit[]>([]);
  readonly site = signal<Site | null>(null);
  readonly token = signal<string | null>(null);
  readonly copied = signal(false);
  readonly firstData = signal(false);
  readonly assetCount = signal(0);
  readonly error = signal<string | null>(null);
  readonly busy = signal(false);
  readonly usvAddress = API_BASE_URL;
  private poll?: Subscription;

  readonly form = this.fb.nonNullable.group({
    business_unit_id: [''],
    new_business_unit: [''],
    site_code: ['', [Validators.required, Validators.pattern(/^[A-Z]{2,5}-\d{2,4}$/)]],
    name: ['', Validators.required],
    criticality: ['high'],
    timezone: [Intl.DateTimeFormat().resolvedOptions().timeZone],
    tribot_url: [''],
  });

  ngOnInit(): void {
    this.fleet.businessUnits().subscribe((u) => this.units.set(u));
  }

  ngOnDestroy(): void {
    this.poll?.unsubscribe();
  }

  create(): void {
    const v = this.form.getRawValue();
    if (this.form.invalid || (!v.business_unit_id && !v.new_business_unit.trim())) {
      this.error.set('Choose or name a business unit, and give a site code like PWR-01 and a name.');
      return;
    }
    this.error.set(null);
    this.busy.set(true);
    const withBu = (buId: string) =>
      this.fleet
        .createSite({
          site_code: v.site_code,
          name: v.name,
          business_unit_id: buId,
          criticality: v.criticality || null,
          timezone: v.timezone || null,
          tribot_url: v.tribot_url.trim() || null,
        })
        .pipe(switchMap((site) => {
          this.site.set(site);
          return this.fleet.issueToken(site.site_id);
        }))
        .subscribe({
          next: (t) => {
            this.token.set(t.token ?? null);
            this.step.set(2);
            this.busy.set(false);
            this.selection.refresh();
          },
          error: (e: HttpErrorResponse) => this.fail(e),
        });
    if (v.business_unit_id) {
      withBu(v.business_unit_id);
    } else {
      this.fleet.createBusinessUnit(v.new_business_unit.trim()).subscribe({
        next: (bu) => withBu(bu.business_unit_id),
        error: (e: HttpErrorResponse) => this.fail(e),
      });
    }
  }

  copyToken(): void {
    const t = this.token();
    if (t) {
      navigator.clipboard?.writeText(t).then(() => this.copied.set(true));
    }
  }

  tokenSaved(): void {
    // the token can never be shown again: drop it from the page
    this.token.set(null);
    this.step.set(3);
    const site = this.site()!;
    this.poll = interval(10000)
      .pipe(switchMap(() => this.fleet.assets({ siteIds: [site.site_id], limit: 1 })))
      .subscribe((page) => {
        this.assetCount.set(page.total);
        if (page.total > 0) {
          this.firstData.set(true);
          this.poll?.unsubscribe();
        }
      });
  }

  private fail(e: HttpErrorResponse): void {
    this.busy.set(false);
    this.error.set(e.error?.error?.message ?? 'Could not create the site.');
  }
}
