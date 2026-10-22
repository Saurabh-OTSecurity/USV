// Models for the multi-site operations screens (USV O&M Manual sections 3-7, 10-11).

export interface BusinessUnit {
  business_unit_id: string;
  tenant_id: string;
  name: string;
  status: string;
}

export interface FleetAsset {
  asset_id: string;
  site_id: string;
  source_asset_id: string;
  name: string | null;
  device_type: string | null;
  risk_level: string | null;
  industrial_zone: string | null;
  purdue_level: number | null;
  lifecycle_state: 'active' | 'silent' | 'missing_from_tribot';
  silent_since: string | null;
  first_seen_at: string;
  last_seen_at: string;
}

export interface FleetAlert {
  alert_id: string;
  site_id: string;
  source_alert_id: string;
  severity: string | null;
  status: string | null;
  category: string | null;
  cve_id: string | null;
  title: string | null;
  occurred_at: string | null;
  asset_id: string | null;
  closed_reason: string | null;
}

export interface FleetIncident {
  incident_id: string;
  site_id: string;
  source_incident_id: string;
  title: string | null;
  status: string | null;
  severity: string | null;
  owner: string | null;
  updated_at?: string | null;
}

export interface FleetRemediation {
  remediation_id: string;
  site_id: string;
  source_remediation_id: string;
  title: string | null;
  status: string | null;
  owner: string | null;
  planned_date: string | null;
}

export interface TopologyLink {
  link_id: string;
  site_id: string;
  source_link_id: string;
  source_asset_id: string;
  target_asset_id: string;
  protocol: string | null;
  ports: number[];
}

export interface CorrelationGroup {
  correlation_group_id: string;
  correlation_key: string;
  title: string | null;
  member_ids: string[];
  site_ids: string[];
}

export interface Tombstone {
  site_id: string;
  source_asset_id: string;
  asset_name: string | null;
  reason: string | null;
  decommissioned_by: string | null;
  decommissioned_at: string;
  origin: string;
  restored_at: string | null;
}

export interface Page<T> {
  rows: T[];
  total: number;
}

export interface UsvAlert {
  usv_alert_id: string;
  site_id: string | null;
  rule_id: string;
  category: string;
  severity: 'Info' | 'Warning' | 'Critical';
  title: string;
  detail: Record<string, unknown>;
  status: 'open' | 'acknowledged' | 'closed';
  event_only: boolean;
  occurrence_count: number;
  opened_at: string;
  last_seen_at: string;
  closed_at: string | null;
}

export interface SiteStateRow {
  site_id: string;
  site_code: string;
  name: string;
  state: 'healthy' | 'silent' | 'disconnected' | 'waiting_first_data';
  state_since: string | null;
  last_contact_at: string | null;
}

export interface HealthSummary {
  generated_at: string;
  site_counts: Record<string, number>;
  sites: SiteStateRow[];
  ingestion?: { pending: number; delay_seconds: number };
  database?: { ok?: boolean; latency_ms?: number; error?: string };
  database_disk?: { configured: boolean; free_percent?: number; path?: string };
  certificate?: { configured: boolean; days_left?: number; not_after?: string; error?: string };
  backup?: { configured: boolean; age_hours?: number | null; last_backup_at?: string | null };
  api?: { requests: number; server_errors: number; error_percent: number };
  open_alerts_by_severity?: Record<string, number>;
}

export interface Notification {
  notification_id: string;
  usv_alert_id: string | null;
  level: string;
  title: string;
  created_at: string;
  read_at: string | null;
}

export interface IngestionToken {
  token_id: string;
  site_id: string;
  status: string;
  created_at: string;
  revoked_at: string | null;
  last_used_at: string | null;
  token?: string;
}

export interface Downtime {
  downtime_id: string;
  site_id: string;
  starts_at: string;
  ends_at: string;
  reason: string;
}

export interface MonitoringLimits {
  site_id: string | null;
  configured: Record<string, number | null>;
  effective: Record<string, number>;
  bounds: Record<string, [number, number]>;
}

export interface PendingReset {
  request_id: string;
  username: string;
  role: string;
  site_id: string | null;
  requested_at: string;
  source_ip: string | null;
  escalated: boolean;
  approvals: number;
  required_approvals: number;
}

export interface BreakGlassRequest {
  request_id: string;
  site_id: string;
  status: string;
  reason: string;
  approvals: { user_id: string; side: string; at: string }[];
  created_at: string;
  opened_at: string | null;
}

export interface Approver {
  approver_id: string;
  level: 'platform' | 'customer' | 'business_unit' | 'site';
  scope_id: string | null;
  user_id: string;
  is_backup: boolean;
}

export interface Customer {
  tenant_id: string;
  tenant_code: string;
  name: string;
  database_name: string;
  status: string;
}

export interface SiteSummary {
  site_id: string;
  site_code: string;
  name: string;
  business_unit_id: string;
  assets: number;
  silent_assets: number;
  missing_assets: number;
  open_alerts: Record<string, number>;
  open_incidents: number;
  open_remediations: number;
  state: 'healthy' | 'silent' | 'disconnected' | 'waiting_first_data';
  last_contact_at: string | null;
}
