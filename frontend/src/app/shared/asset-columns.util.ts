// The Asset Inventory column catalogue. The catalogue itself mirrors Tribot's
// ASSET_COLUMN_CATALOG in frontend/src/pages/AssetInventory.jsx (parity gap
// A-06); the *defaults* deliberately do not -- see DEFAULT_ASSET_COLUMNS below.
// Every column here maps to a field map_asset() already emits.
//
// `ip` is pinned first and is NOT in the catalogue, exactly as in Tribot --
// it is the asset's identity in the table and cannot be turned off. This
// matters more in USV than it does in Tribot: `hostname` is the literal string
// "Unknown" for an unidentified device, so a table keyed on hostname alone
// shows a column of "Unknown" and no way to tell the rows apart.

import { TribotAsset } from './tribot.models';

export interface AssetColumn {
  /** Key on TribotAsset. */
  key: keyof TribotAsset | string;
  label: string;
  /** The `filterBy` key for this column, when it can be filtered server-side. */
  filterField?: string;
  /** Right-align and use tabular figures. */
  numeric?: boolean;
}

/** Always shown, always first. */
export const PINNED_COLUMN: AssetColumn = { key: 'ip', label: 'IP', filterField: 'ip' };

export const ASSET_COLUMN_CATALOG: AssetColumn[] = [
  { key: 'primaryDomain', label: 'Domain', filterField: 'primaryDomain' },
  { key: 'functionalCategory', label: 'Category', filterField: 'functionalCategory' },
  // Labelled "Manufacturer" although the field is `vendor` (2026-09-19). On a
  // MAC lookup the two are the same string: device_fingerprint_engine.py hands
  // the identical mac_vendor value to both the vendor and manufacturer
  // evidence, and RefMacVendor's curated short-brand column is never read. So
  // this is a rename, not a change of source -- `vendor` stays the field, the
  // filterField and the API parameter, which matters because CVE and
  // end-of-life matching key off it.
  { key: 'vendor', label: 'Manufacturer', filterField: 'vendor' },
  // The genuinely separate field. Only the OWAIS/WinRM ingest writes it, from
  // WMI SystemInfo, leaving `vendor` alone -- hence the qualifier, so two
  // columns are not both called "Manufacturer". Near-empty until that ingest
  // has run.
  { key: 'manufacturer', label: 'Manufacturer (WMI)', filterField: 'manufacturer' },
  { key: 'productFamily', label: 'Product Family', filterField: 'productFamily' },
  { key: 'modelNumber', label: 'Model', filterField: 'modelNumber' },
  { key: 'productSeries', label: 'Series', filterField: 'productSeries' },
  { key: 'deviceType', label: 'Type', filterField: 'deviceType' },
  { key: 'lifecycle', label: 'Lifecycle' },
  { key: 'riskScore', label: 'Risk', numeric: true },
  { key: 'cveCount', label: 'CVEs', numeric: true },
  { key: 'confidenceScore', label: 'Conf', numeric: true },
  { key: 'mac', label: 'MAC Address', filterField: 'mac' },
  { key: 'hostname', label: 'Hostname', filterField: 'hostname' },
  { key: 'firmwareVersion', label: 'Firmware', filterField: 'firmwareVersion' },
  { key: 'hardwareRevision', label: 'Hardware Rev', filterField: 'hardwareRevision' },
  { key: 'serialNumber', label: 'Serial Number', filterField: 'serialNumber' },
  { key: 'operatingSystem', label: 'Operating System', filterField: 'operatingSystem' },
  { key: 'industrialZone', label: 'Industrial Zone', filterField: 'industrialZone' },
  { key: 'safetyImpact', label: 'Safety Impact', filterField: 'safetyImpact' },
  { key: 'internetExposure', label: 'Internet Exposure', filterField: 'internetExposure' },
  { key: 'subnet', label: 'Subnet', filterField: 'subnet' },
  { key: 'sourceInterface', label: 'Interface', filterField: 'sourceInterface' },
  { key: 'notes', label: 'Description' },
  // Present in USV beyond Tribot's own catalogue, because map_asset already
  // carries them and an operator asked for every available column.
  { key: 'protocols', label: 'Protocols', filterField: 'protocols' },
  { key: 'riskLevel', label: 'Risk Level', filterField: 'riskLevel' },
  { key: 'operationalCriticality', label: 'Criticality', filterField: 'operationalCriticality' },
  { key: 'osVersion', label: 'OS Version', filterField: 'osVersion' },
  { key: 'role', label: 'Role', filterField: 'role' },
  { key: 'macVendor', label: 'MAC Vendor', filterField: 'macVendor' },
  { key: 'healthStatus', label: 'Health', filterField: 'healthStatus' },
  { key: 'lastSeen', label: 'Last seen' },
  { key: 'firstSeen', label: 'First seen' },
];

/**
 * The union of Tribot's defaults and the columns USV's own table always showed.
 *
 * Deliberately NOT a copy of Tribot's DEFAULT_ASSET_COLUMNS. That set is 11
 * classification columns and carries no MAC, zone, protocols or last-seen --
 * all four of which USV's table showed as fixed columns before 2026-09-18.
 * Aligning the defaults to Tribot's silently dropped them, which is a
 * regression for an operator who had them, so the default is the union:
 * Tribot's 11 plus those four.
 *
 * Ordered identity -> classification -> risk -> network/time. With the pinned
 * IP and the Name column that is 17; the table scrolls horizontally and the
 * Columns picker trims it back.
 */
export const DEFAULT_ASSET_COLUMNS = [
  'mac',
  'primaryDomain', 'functionalCategory',
  'vendor', 'productFamily', 'modelNumber', 'productSeries', 'deviceType',
  'lifecycle',
  'riskScore', 'cveCount', 'confidenceScore',
  'industrialZone', 'protocols', 'lastSeen',
];

export const COLUMN_BY_KEY: Record<string, AssetColumn> = Object.fromEntries(
  [PINNED_COLUMN, ...ASSET_COLUMN_CATALOG].map((c) => [c.key as string, c]),
);

/**
 * AssetOverride field_names, in the API's snake_case, keyed by the camelCase
 * column they override. Drives the "manually entered value" treatment, which
 * mirrors Tribot's COLUMN_OVERRIDE_FIELD (parity gap A-03).
 */
export const COLUMN_OVERRIDE_FIELD: Record<string, string> = {
  hostname: 'hostname',
  vendor: 'vendor',
  manufacturer: 'manufacturer',
  modelNumber: 'model_number',
  serialNumber: 'serial_number',
  firmwareVersion: 'firmware_version',
  industrialZone: 'industrial_zone',
  safetyImpact: 'safety_level',
  operationalCriticality: 'operational_criticality',
  notes: 'notes',
};

export function isOverridden(asset: TribotAsset, columnKey: string): boolean {
  const field = COLUMN_OVERRIDE_FIELD[columnKey];
  return !!field && Array.isArray(asset.overriddenFields) && asset.overriddenFields.includes(field);
}

/** Display value for one cell. Arrays join; null/blank become an em dash. */
export function cellValue(asset: TribotAsset, columnKey: string): string {
  const raw = (asset as unknown as Record<string, unknown>)[columnKey];
  if (Array.isArray(raw)) return raw.length ? raw.join(', ') : '—';
  if (raw === null || raw === undefined || raw === '') return '—';
  return String(raw);
}
