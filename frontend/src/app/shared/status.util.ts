export type StatusVariant = 'success' | 'warning' | 'danger' | 'neutral';

const SUCCESS_VALUES = new Set(['active', 'healthy', 'configured', 'success', 'ready']);
const WARNING_VALUES = new Set(['degraded', 'warning', 'pending']);
const DANGER_VALUES = new Set(['error', 'failed', 'failure', 'inactive', 'disabled', 'unavailable']);

export function statusVariant(status: string | null | undefined): StatusVariant {
  if (!status) {
    return 'neutral';
  }
  const normalized = status.toLowerCase();
  if (SUCCESS_VALUES.has(normalized)) return 'success';
  if (WARNING_VALUES.has(normalized)) return 'warning';
  if (DANGER_VALUES.has(normalized)) return 'danger';
  return 'neutral';
}
