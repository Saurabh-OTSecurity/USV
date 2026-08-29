import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { DatePipe } from '@angular/common';

import { UsvService } from '../../shared/usv.service';
import { Usv } from '../../shared/models';
import { StatusBadgeComponent } from '../../shared/status-badge/status-badge.component';

@Component({
  selector: 'app-usv-list',
  standalone: true,
  imports: [RouterLink, DatePipe, StatusBadgeComponent],
  templateUrl: './usv-list.component.html',
})
export class UsvListComponent implements OnInit {
  private readonly usvService = inject(UsvService);

  readonly usvs = signal<Usv[]>([]);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);

  ngOnInit(): void {
    this.usvService.list().subscribe({
      next: (usvs) => {
        this.usvs.set(usvs);
        this.loading.set(false);
      },
      error: () => {
        this.error.set('Unable to load USV instances from the backend.');
        this.loading.set(false);
      },
    });
  }
}
