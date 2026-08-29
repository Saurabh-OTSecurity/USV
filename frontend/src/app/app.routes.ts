import { Routes } from '@angular/router';

import { LoginComponent } from './features/login/login.component';
import { ShellComponent } from './layout/shell.component';
import { DashboardComponent } from './features/dashboard/dashboard.component';
import { SiteListComponent } from './features/site/site-list.component';
import { SiteDetailComponent } from './features/site/site-detail.component';
import { UsvListComponent } from './features/usv/usv-list.component';
import { UsvDetailComponent } from './features/usv/usv-detail.component';
import { IntegrationsListComponent } from './features/integrations/integrations-list.component';
import { IntegrationDetailComponent } from './features/integrations/integration-detail.component';
import { UsersComponent } from './features/users/users.component';
import { authGuard } from './core/auth/auth.guard';
import { roleGuard } from './core/auth/role.guard';

const PLATFORM_ADMIN_ROLE = 'usv_platform_admin';

export const routes: Routes = [
  { path: 'login', component: LoginComponent },
  {
    path: '',
    component: ShellComponent,
    canActivate: [authGuard],
    children: [
      { path: '', redirectTo: 'dashboard', pathMatch: 'full' },
      { path: 'dashboard', component: DashboardComponent },
      { path: 'site', component: SiteListComponent },
      { path: 'site/:id', component: SiteDetailComponent },
      { path: 'usv', component: UsvListComponent },
      { path: 'usv/:id', component: UsvDetailComponent },
      { path: 'integrations', component: IntegrationsListComponent },
      { path: 'integrations/:id', component: IntegrationDetailComponent },
      {
        path: 'users',
        component: UsersComponent,
        canActivate: [roleGuard([PLATFORM_ADMIN_ROLE])],
      },
    ],
  },
  { path: '**', redirectTo: 'login' },
];
