// The canonical 5-tier Purdue scheme, mirroring Tribot's
// frontend/src/constants/purdueTiers.js (which in turn mirrors its backend's
// intel/purdue.py). Parity gap DT-01.
//
// Colours are expressed against USV's own dark palette rather than copied from
// Tribot's light one: the tiers must be *distinguishable in the same order*,
// not the same hex on a different background.
//
// Display labels are only defaults. Tribot's are admin-editable and come from
// GET /api/v1/tribot/topology/purdue-levels (gap DT-02) -- these are the
// fallback for a tier that call has no row for.

export interface PurdueTier {
  key: string;
  /** Position used for ordering and for policy-violation distance. 0 = L1. */
  numeric: number;
  defaultLabel: string;
  accent: string;
  band: string;
}

export const PURDUE_TIERS: PurdueTier[] = [
  { key: 'L1', numeric: 0, defaultLabel: 'L1 – Basic Control & Physical Process', accent: '#3fb96c', band: 'rgba(63,185,108,0.07)' },
  { key: 'L2', numeric: 1, defaultLabel: 'L2 – Area Supervisory Control', accent: '#2fbf9c', band: 'rgba(47,191,156,0.07)' },
  { key: 'L3', numeric: 2, defaultLabel: 'L3 – Site Operations', accent: '#5b9bd9', band: 'rgba(91,155,217,0.07)' },
  { key: 'L3.5', numeric: 3, defaultLabel: 'L3.5 – Industrial DMZ', accent: '#8b5cf6', band: 'rgba(139,92,246,0.07)' },
  { key: 'L4', numeric: 4, defaultLabel: 'L4 – External / Enterprise / Internet', accent: '#a79cb3', band: 'rgba(167,156,179,0.07)' },
];

export const PURDUE_TIER_BY_NUMERIC: Record<number, PurdueTier> = Object.fromEntries(
  PURDUE_TIERS.map((t) => [t.numeric, t]),
);

export const PURDUE_TIER_BY_KEY: Record<string, PurdueTier> = Object.fromEntries(
  PURDUE_TIERS.map((t) => [t.key, t]),
);

// Device type -> canonical tier key. Mirrors Tribot's DEVICE_TYPE_TO_TIER_KEY
// exactly. Used ONLY as a fallback when a node carries no zone Purdue level --
// the backend is the source of truth.
export const DEVICE_TYPE_TO_TIER_KEY: Record<string, string> = {
  Sensor: 'L1', Actuator: 'L1', 'Smart Device': 'L1', VFD: 'L1', Drive: 'L1',
  PLC: 'L1', RTU: 'L1', IED: 'L1', 'Safety Controller': 'L1', 'Safety PLC': 'L1',
  'DCS Controller': 'L1', 'CNC Controller': 'L1', 'Serial Server': 'L1',
  HMI: 'L2', Workstation: 'L2', 'Engineering Workstation': 'L2',
  'Protocol Gateway': 'L2', Camera: 'L2', 'Building Controller': 'L2',
  Historian: 'L3', 'SCADA Server': 'L3', 'OPC Server': 'L3', 'OPC UA': 'L3',
  'Database Server': 'L3', 'Domain Controller': 'L3', Server: 'L3',
  'Windows Server': 'L3', 'Linux Server': 'L3', 'IoT Gateway': 'L3',
  Switch: 'L3', Router: 'L3', 'Wireless AP': 'L3',
  Firewall: 'L3.5', 'Protocol Gateway VPN': 'L3.5',
  'Access Point': 'L4', Printer: 'L4',
};

/**
 * A device whose tier cannot be established from either its zone or its device
 * type. Given its own lane rather than being folded into L1.
 *
 * Tribot's own screen defaults these into a real tier, which reads as a
 * positive claim about where a device sits in the plant. On a segmentation
 * diagram that claim is the whole point, so an unknown device is shown as
 * unknown -- an operator can see there is classification work to do instead of
 * trusting a guess.
 */
export const UNCLASSIFIED_TIER: PurdueTier = {
  key: 'unclassified',
  numeric: -1,
  defaultLabel: 'Unclassified – tier not established',
  accent: '#a79cb3',
  band: 'rgba(167,156,179,0.05)',
};

/**
 * Resolve a node's tier. Prefers the Purdue level the backend supplied for its
 * zone, then the device-type table, then UNCLASSIFIED_TIER.
 */
export function resolveTier(purdueLevel: number | null | undefined, deviceType: string | null): PurdueTier {
  if (purdueLevel !== null && purdueLevel !== undefined && PURDUE_TIER_BY_NUMERIC[purdueLevel]) {
    return PURDUE_TIER_BY_NUMERIC[purdueLevel];
  }
  const key = deviceType ? DEVICE_TYPE_TO_TIER_KEY[deviceType] : undefined;
  return (key && PURDUE_TIER_BY_KEY[key]) || UNCLASSIFIED_TIER;
}

// Device-type colour map, mirroring Tribot's DEVICE_COLORS. A node with an
// unmapped type falls back to the muted text colour rather than inheriting a
// neighbouring type's meaning.
export const DEVICE_COLORS: Record<string, string> = {
  PLC: '#3fb96c', RTU: '#3fb96c', IED: '#3fb96c',
  HMI: '#5b9bd9', 'Engineering Workstation': '#5b9bd9',
  'SCADA Server': '#c0392b', 'OPC Server': '#d0973a',
  Switch: '#8b5cf6', Router: '#8b5cf6', Firewall: '#8b5cf6',
  'Database Server': '#ec4899', Historian: '#ec4899',
  'Windows Server': '#6366f1', 'Linux Server': '#6366f1',
  Server: '#6366f1', 'Domain Controller': '#6366f1',
  'Wireless AP': '#2fbf9c', Camera: '#84cc16', Printer: '#a8a29e',
  'Safety Controller': '#c0392b', 'DCS Controller': '#f97316',
  Sensor: '#14b8a6', Actuator: '#f97316',
  'Protocol Gateway': '#8b5cf6', 'Serial Server': '#a79cb3',
  'IoT Gateway': '#2fbf9c', 'Smart Device': '#5b9bd9',
  'Building Controller': '#84cc16', 'CNC Controller': '#f97316',
};

export function deviceColor(deviceType: string | null): string {
  return (deviceType && DEVICE_COLORS[deviceType]) || '#a79cb3';
}

// ── Communication classification (gap DT-04) ──
//
// Mirrors Tribot's COMM_LINE_STYLES. Tribot derives these client-side from the
// topology edges plus alerts plus zone Purdue levels; USV now has all three
// (the zone ids arrive on each link, gap DT-11), so the same derivation runs
// here rather than the single undifferentiated grey line USV drew before.

export type CommType = 'baseline' | 'new_comm' | 'high_frequency' | 'suspicious';

export interface CommStyle {
  stroke: string;
  width: number;
  dash: string;
  label: string;
}

export const COMM_STYLES: Record<CommType, CommStyle> = {
  baseline: { stroke: '#3fb96c', width: 1.6, dash: '', label: 'Baseline' },
  new_comm: { stroke: '#d0973a', width: 1.8, dash: '', label: 'Cross-zone' },
  high_frequency: { stroke: '#f97316', width: 2.4, dash: '', label: 'High frequency' },
  suspicious: { stroke: '#c0392b', width: 2.4, dash: '6,4', label: 'Suspicious' },
};

/** Tribot's own threshold for a high-frequency conversation. */
export const HIGH_FREQUENCY_PACKETS = 10000;
