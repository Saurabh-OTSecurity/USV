export interface Site {
  site_id: string;
  business_unit_id?: string;
  tribot_url?: string | null;
  site_code: string;
  name: string;
  description: string | null;
  timezone: string | null;
  criticality: string | null;
  status: string | null;
}

export interface Usv {
  usv_id: string;
  site_id: string;
  usv_code: string;
  hostname: string | null;
  installation_id: string | null;
  version: string | null;
  status: string | null;
  last_heartbeat: string | null;
}

export interface Integration {
  integration_id: string;
  site_id: string | null;
  integration_type: string | null;
  name: string | null;
  provider: string | null;
  version: string | null;
  status: string | null;
  is_fixed_engine: boolean;
  last_success_at: string | null;
  last_error_at: string | null;
}
