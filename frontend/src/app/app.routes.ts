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
import { TribotShellComponent } from './features/ot-asset/tribot/tribot-shell.component';
import { TribotAssetListComponent } from './features/ot-asset/tribot/assets/tribot-asset-list.component';
import { TribotAssetDetailComponent } from './features/ot-asset/tribot/assets/tribot-asset-detail.component';
import { TribotTopologyComponent } from './features/ot-asset/tribot/topology/tribot-topology.component';
import { TribotAlertListComponent } from './features/ot-asset/tribot/alerts/tribot-alert-list.component';
import { TribotAlertDetailComponent } from './features/ot-asset/tribot/alerts/tribot-alert-detail.component';
import { TribotVulnerabilityListComponent } from './features/ot-asset/tribot/vulnerabilities/tribot-vulnerability-list.component';
import { TribotCaseBoardComponent } from './features/ot-asset/tribot/cases/tribot-case-board.component';
import { AddSiteComponent } from './features/onboarding/add-site.component';
import { BusinessViewComponent } from './features/business/business-view.component';
import { SiteFullComponent } from './features/business/site-full.component';
import { SiteLifecycleComponent } from './features/business/site-lifecycle.component';
import { FleetListsComponent } from './features/fleet/fleet-lists.component';
import { PlatformHealthComponent } from './features/monitoring/platform-health.component';
import { ChangePasswordComponent } from './features/identity/change-password.component';
import { ForgotPasswordComponent } from './features/identity/forgot-password.component';
import { ShareOpenComponent } from './features/identity/share-open.component';
import { ApprovalsComponent } from './features/identity/approvals.component';
import { TribotSsoComponent } from './features/identity/tribot-sso.component';
import { CustomersComponent } from './features/identity/customers.component';
import { authGuard } from './core/auth/auth.guard';
import { roleGuard } from './core/auth/role.guard';

const PLATFORM_ADMIN_ROLE = 'usv_platform_admin';

export const routes: Routes = [
  { path: 'login', component: LoginComponent },
  // no login needed: forgot password and one-time secret links (manual sections 10-11)
  { path: 'forgot-password', component: ForgotPasswordComponent },
  { path: 'share/:token', component: ShareOpenComponent },
  {
    path: '',
    component: ShellComponent,
    canActivate: [authGuard],
    children: [
      { path: '', redirectTo: 'dashboard', pathMatch: 'full' },
      { path: 'dashboard', component: DashboardComponent },
      { path: 'site', component: SiteListComponent },
      { path: 'site/new', component: AddSiteComponent },
      { path: 'site/:id', component: SiteDetailComponent },
      { path: 'business', component: BusinessViewComponent },
      {
        // one site, with the OT Asset > Tribot pages fed from its pushed data
        path: 'business/site/:id',
        component: SiteFullComponent,
        children: [
          { path: '', redirectTo: 'assets', pathMatch: 'full' },
          { path: 'assets', component: TribotAssetListComponent },
          { path: 'assets/:id', component: TribotAssetDetailComponent },
          { path: 'topology', component: TribotTopologyComponent },
          { path: 'alerts', component: TribotAlertListComponent },
          { path: 'alerts/:id', component: TribotAlertDetailComponent },
          { path: 'vulnerabilities', component: TribotVulnerabilityListComponent },
          { path: 'cases', component: TribotCaseBoardComponent },
          { path: 'lifecycle', component: SiteLifecycleComponent },
        ],
      },
      { path: 'fleet', component: FleetListsComponent },
      { path: 'health', component: PlatformHealthComponent },
      { path: 'approvals', component: ApprovalsComponent },
      { path: 'change-password', component: ChangePasswordComponent },
      { path: 'sso/tribot', component: TribotSsoComponent },
      { path: 'customers', component: CustomersComponent, canActivate: [roleGuard([PLATFORM_ADMIN_ROLE])] },
      { path: 'usv', component: UsvListComponent },
      { path: 'usv/:id', component: UsvDetailComponent },
      { path: 'integrations', component: IntegrationsListComponent },
      { path: 'integrations/:id', component: IntegrationDetailComponent },
      {
        path: 'ot-asset/tribot',
        component: TribotShellComponent,
        children: [
          { path: '', redirectTo: 'assets', pathMatch: 'full' },
          { path: 'assets', component: TribotAssetListComponent },
          { path: 'assets/:id', component: TribotAssetDetailComponent },
          { path: 'topology', component: TribotTopologyComponent },
          { path: 'alerts', component: TribotAlertListComponent },
          { path: 'alerts/:id', component: TribotAlertDetailComponent },
          { path: 'vulnerabilities', component: TribotVulnerabilityListComponent },
          { path: 'cases', component: TribotCaseBoardComponent },
        ],
      },
      {
        path: 'users',
        component: UsersComponent,
        canActivate: [roleGuard([PLATFORM_ADMIN_ROLE, 'usv_customer_admin'])],
      },
    ],
  },
  { path: '**', redirectTo: 'login' },
];
