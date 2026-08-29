import { Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { DatePipe } from '@angular/common';

import { UsvService } from '../../shared/usv.service';
import { Usv } from '../../shared/models';
import { StatusBadgeComponent } from '../../shared/status-badge/status-badge.component';

@Component({
  selector: 'app-usv-detail',
  standalone: true,
  imports: [RouterLink, DatePipe, StatusBadgeComponent],
  templateUrl: './usv-detail.component.html',
})
export class UsvDetailComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly usvService = inject(UsvService);

  readonly usv = signal<Usv | null>(null);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);

  ngOnInit(): void {
    const usvId = this.route.snapshot.paramMap.get('id');
    if (!usvId) {
      this.error.set('No USV id provided.');
      this.loading.set(false);
      return;
    }

    this.usvService.get(usvId).subscribe({
      next: (usv) => {
        this.usv.set(usv);
        this.loading.set(false);
      },
      error: () => {
        this.error.set('USV not found.');
        this.loading.set(false);
      },
    });
  }
}
