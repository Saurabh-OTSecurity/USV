// Maps Tribot's free-text severity/risk-level/status strings onto this app's
// pill-* CSS classes (styles.scss). Tribot's values are lowercase strings
// like "critical"/"high"/"medium"/"low" (severity, riskLevel) — this only
// picks a color, it never changes the displayed text.

export function severityPillClass(value: string | null | undefined): string {
  const normalized = (value ?? '').toLowerCase();
  if (normalized === 'critical' || normalized === 'high') return 'pill-red';
  if (normalized === 'medium') return 'pill-amber';
  if (normalized === 'low') return 'pill-blue';
  if (normalized === 'info' || normalized === 'informational') return 'pill-teal';
  return 'pill-neutral';
}

export function riskLevelPillClass(value: string | null | undefined): string {
  return severityPillClass(value);
}

export function alertStatusPillClass(value: string | null | undefined): string {
  const normalized = (value ?? '').toLowerCase();
  if (normalized === 'new') return 'pill-blue';
  if (normalized === 'investigating') return 'pill-amber';
  if (normalized === 'acknowledged') return 'pill-teal';
  if (normalized === 'resolved') return 'pill-green';
  if (normalized === 'suppressed') return 'pill-neutral';
  return 'pill-neutral';
}

// ── Incident Response vocabulary (gap IR-09) ──
// Mirrors Tribot's features/ir/irConstants.js STATUS_META one-for-one, so a
// case reads the same colour on both products. Tribot's canonical column
// order lives in CASE_STATUSES there; IR_CASE_STATUSES below is that list.

export const IR_CASE_STATUSES = [
  'New',
  'InProgress',
  'Contained',
  'ClosurePending',
  'Closed',
] as const;

export const IR_TIERS = ['L1', 'L2', 'L3'] as const;

const IR_STATUS_LABELS: Record<string, string> = {
  New: 'New',
  InProgress: 'In Progress',
  Contained: 'Contained',
  ClosurePending: 'Closure Pending',
  Closed: 'Closed',
};

export function irStatusLabel(value: string | null | undefined): string {
  const key = value ?? '';
  return IR_STATUS_LABELS[key] ?? key ?? '—';
}

export function irStatusPillClass(value: string | null | undefined): string {
  switch (value) {
    case 'New':
      return 'pill-blue';
    case 'InProgress':
      return 'pill-amber';
    case 'Contained':
      return 'pill-teal';
    case 'ClosurePending':
      return 'pill-red';
    case 'Closed':
      return 'pill-green';
    default:
      return 'pill-neutral';
  }
}

export function irTierPillClass(value: string | null | undefined): string {
  switch (value) {
    case 'L1':
      return 'pill-blue';
    case 'L2':
      return 'pill-amber';
    case 'L3':
      return 'pill-red';
    default:
      return 'pill-neutral';
  }
}
