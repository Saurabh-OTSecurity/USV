import { Component, Input } from '@angular/core';

import { statusVariant } from '../status.util';

@Component({
  selector: 'app-status-badge',
  standalone: true,
  templateUrl: './status-badge.component.html',
  styleUrl: './status-badge.component.scss',
})
export class StatusBadgeComponent {
  @Input() status: string | null | undefined = null;

  get variant(): string {
    return statusVariant(this.status);
  }

  get displayText(): string {
    return this.status ?? 'unknown';
  }
}
