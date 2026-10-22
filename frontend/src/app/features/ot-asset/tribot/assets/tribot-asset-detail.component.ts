import { Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { DatePipe } from '@angular/common';
import { forkJoin } from 'rxjs';

import { TribotService } from '../../../../shared/tribot.service';
import { TribotContextService } from '../../../../shared/tribot-context.service';
import { TribotAlert, TribotAsset, TribotVulnerability } from '../../../../shared/tribot.models';
import { riskLevelPillClass, severityPillClass } from '../../../../shared/tribot-pill.util';
import { TribotAssetSoftwareComponent } from './tribot-asset-software.component';

type TabKey = 'overview' | 'vulnerabilities' | 'alerts' | 'software';

@Component({
  selector: 'app-tribot-asset-detail',
  standalone: true,
  imports: [RouterLink, DatePipe, TribotAssetSoftwareComponent],
  templateUrl: './tribot-asset-detail.component.html',
})
export class TribotAssetDetailComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly tribotService = inject(TribotService);
  readonly ctx = inject(TribotContextService);

  readonly asset = signal<TribotAsset | null>(null);
  readonly vulnerabilities = signal<TribotVulnerability[]>([]);
  readonly alerts = signal<TribotAlert[]>([]);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly activeTab = signal<TabKey>('overview');

  readonly riskLevelPillClass = riskLevelPillClass;
  readonly severityPillClass = severityPillClass;

  ngOnInit(): void {
    const assetId = this.route.snapshot.paramMap.get('id');
    if (!assetId) {
      this.error.set('No asset id provided.');
      this.loading.set(false);
      return;
    }

    forkJoin({
      asset: this.tribotService.getAsset(assetId),
      vulnerabilities: this.tribotService.listVulnerabilities({ assetId, pageSize: 100 }),
      alerts: this.tribotService.listAlerts({ assetId, pageSize: 100 }),
    }).subscribe({
      next: ({ asset, vulnerabilities, alerts }) => {
        this.asset.set(asset.data);
        this.vulnerabilities.set(vulnerabilities.data);
        this.alerts.set(alerts.data);
        this.loading.set(false);
      },
      error: () => {
        this.error.set('Asset not found in Tribot, or Tribot is unreachable.');
        this.loading.set(false);
      },
    });
  }

  setTab(tab: TabKey): void {
    this.activeTab.set(tab);
  }
}
