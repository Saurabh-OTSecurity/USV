import { Component, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { TribotContextService } from '../../../shared/tribot-context.service';

@Component({
  selector: 'app-tribot-shell',
  standalone: true,
  imports: [RouterLink, RouterLinkActive, RouterOutlet],
  templateUrl: './tribot-shell.component.html',
})
export class TribotShellComponent {
  constructor() {
    // these pages show the one live Tribot, not a pushed site
    inject(TribotContextService).siteId.set(null);
  }
}
