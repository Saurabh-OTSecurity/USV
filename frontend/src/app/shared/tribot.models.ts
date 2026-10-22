// Shapes mirror Tribot's External Data API response fields exactly (Section 4
// of Triot_Detection-Engine_Api/Specifications/
// TRIBOT_EXTERNAL_DATA_API_ARCHITECTURE_v1.0.md, plus the additive rounds
// recorded in Tribot's integration/mapping.py) as proxied by USV's backend at
// /api/v1/tribot/*. No field here is invented.
//
// 2026-09-16 (parity gap P-08): regenerated against mapping.py's actual
// output. The previous revision declared 24 asset fields and predated roughly
// twenty-five additions, so fields that arrived on every response were
// unreachable from any template -- which is all gaps A-09, A-10 and DT-03
// actually were. Keep this file generated from mapping.py, not hand-edited.

export interface TribotPagination {
  nextCursor: string | null;
  pageSize: number;
  /** Total rows matching the current filter, across all pages (gap A-14). */
  totalCount: number;
}

export interface TribotListResponse<T> {
  data: T[];
  pagination: TribotPagination;
  requestId: string;
}

export interface TribotItemResponse<T> {
  data: T;
  requestId: string;
}

export interface TribotEolStatus {
  supportStatus: string | null;
  eolDate: string | null;
  eosDate: string | null;
}

/** Saved x/y canvas position from Tribot's Digital Twin (gap DT-03). */
export interface TribotDigitalTwinPosition {
  x: number;
  y: number;
}

export interface TribotAsset {
  /** Raw numeric primary key. Provenance only -- assetId is the identity. */
  id: number;
  assetId: string;
  fingerprint: string | null;
  ip: string | null;
  mac: string | null;
  macVendor: string | null;
  hostname: string | null;
  vendor: string | null;
  manufacturer: string | null;
  deviceType: string | null;
  role: string | null;
  controllerType: string | null;
  operatingSystem: string | null;
  osVersion: string | null;
  firmwareVersion: string | null;
  serialNumber: string | null;
  modelNumber: string | null;
  primaryDomain: string | null;
  domainConfidence: number | null;
  riskScore: number | null;
  riskLevel: string | null;
  confidenceScore: number | null;
  operationalCriticality: string | null;
  industrialZone: string | null;
  protocols: string[];
  firstSeen: string | null;
  lastSeen: string | null;
  cveCount: number;
  findingsCount: number;
  eolCount: number;
  gateway: string | null;
  vlan: string | null;
  packetCount: number | null;

  // ── Operator-edited metadata (gaps A-01/A-02/A-03) ──
  /** Description. Override-only -- no backing column on the asset. */
  notes: string | null;
  /**
   * AssetOverride field_names actually overridden on this asset, e.g.
   * ["vendor", "notes"]. Drives the "manually entered value" treatment.
   * NB these are the API's snake_case override keys, not the camelCase field
   * names above -- "safety_level" overrides `safetyImpact`.
   */
  overriddenFields: string[];

  // ── Classification and context ──
  functionalCategory: string | null;
  productFamily: string | null;
  productSeries: string | null;
  hardwareRevision: string | null;
  safetyImpact: string | null;
  internetExposure: string | null;
  subnet: string | null;
  /** Capture interface. Disambiguates the same IP reused across zones (A-09). */
  sourceInterface: string | null;
  healthScore: number | null;
  healthStatus: string | null;
  riskFactors: unknown;
  digitalTwinPosition: TribotDigitalTwinPosition | null;

  // ── TrustSweep collection provenance (gap A-16) ──
  collectionMethod: string | null;
  collectionOperatorId: string | null;
  lastInventoryAt: string | null;

  // ── Identification confidence breakdown (gap A-04) ──
  vendorConfidence: number;
  modelConfidence: number;
  osConfidence: number;
  firmwareConfidence: number;
  hardwareConfidence: number;
  confidenceReason: string | null;

  // ── Detail-panel fields (gap A-05) ──
  openPorts: number[];
  domainEvidence: string[];
  recommendations: string[];
  normalizationStatus: string | null;
  observedIpCount: number;
  overallAssetConfidence: number | null;

  /** Omitted entirely when the asset has no end-of-life record. */
  eolStatus?: TribotEolStatus;
}

/** One distinct value of a filterable column, with how many assets carry it. */
export interface TribotFacetValue {
  value: string;
  count: number;
}

/** GET /api/v1/tribot/assets/facets (gap A-08). */
export interface TribotAssetFacets {
  field: string;
  /** Ordered by count descending. NULL and blank fold into one "Unknown". */
  values: TribotFacetValue[];
}

/** GET /api/v1/tribot/assets/summary (gap A-07). Whole session, unfiltered. */
export interface TribotAssetSummary {
  total: number;
  byDomain: Record<string, number>;
  byRiskLevel: Record<string, number>;
  byDeviceType: Record<string, number>;
  riskCriticalOrHigh: number;
  withCves: number;
  withEol: number;
}

export interface TribotInstalledSoftware {
  softwareId: string;
  displayName: string | null;
  displayVersion: string | null;
  publisher: string | null;
  installDate: string | null;
  collectedAt: string | null;
}

export interface TribotInstalledPatch {
  patchId: string;
  hotfixId: string | null;
  description: string | null;
  installedOn: string | null;
  collectedAt: string | null;
}

export interface TribotVulnerability {
  vulnerabilityId: string;
  cveId: string | null;
  title: string | null;
  cvssScore: number | null;
  severity: string | null;
  description: string | null;
  mitigation: string | null;
  hasExploit: boolean | null;
  cisaKev: boolean | null;
  assetId: string | null;
  assetIp: string | null;
  assetVendor: string | null;
  assetDeviceType: string | null;
}

/** GET /api/v1/tribot/vulnerabilities/summary (gap V-01). */
export interface TribotVulnerabilitySummary {
  total: number;
  bySeverity: Record<string, number>;
  withExploits: number;
  cisaKev: number;
}

export interface TribotComplianceRefs {
  iec62443Ref: string | null;
  nist80082Ref: string | null;
}

export interface TribotAlert {
  alertId: string;
  ruleId: string | null;
  typeId: string | null;
  severity: string | null;
  title: string | null;
  description: string | null;
  recommendation: string | null;
  category: string | null;
  status: string | null;
  acknowledged: boolean | null;
  assetId: string | null;
  assetIp: string | null;
  assetName: string | null;
  source: string | null;
  destination: string | null;
  protocol: string | null;
  purdueLevel: string | null;
  mitreTechniqueId: string | null;
  mitreTechniqueName: string | null;
  mitreTactic: string | null;
  complianceRefs: TribotComplianceRefs | null;
  createdAt: string | null;
  evidence: unknown;

  // ── Alert-card chip row (gap AL-03) ──
  risk: number | null;
  riskContribution: number | null;
  baselineStatus: string | null;
  /**
   * Which of Tribot's two alert models this row came from (gap AL-04).
   * "behavioral" rows carry MITRE/compliance/Purdue/baseline detail; "legacy"
   * rows carry occurrenceCount instead and leave those null. Both sources emit
   * the same key set, so reading a field never requires branching on this --
   * it is for labelling the row, as Tribot's own UI does.
   */
  sourceType: 'behavioral' | 'legacy' | string | null;
  /** Repeat count. Legacy rows only; always null on a behavioral alert. */
  occurrenceCount: number | null;
  baselineAcceptedBy: string | null;
  baselineAcceptedAt: string | null;
}

/** GET /api/v1/tribot/alerts/summary (gap AL-01). */
export interface TribotAlertSummary {
  severity: Record<string, number>;
  categories: Record<string, number>;
  byStatus: Record<string, number>;
}

export interface TribotZone {
  name: string;
  purdueLevel: string | null;
  color: string | null;
  description: string | null;
}

/** GET /api/v1/tribot/topology/zones (gap DT-15). */
export interface TribotZoneRosterEntry {
  zoneId: string;
  name: string;
  purdueLevel: number | null;
  color: string | null;
  description: string | null;
  sortOrder: number | null;
  assetCount: number;
  /** False when assets reference the zone but no zone record configures it. */
  configured: boolean;
}

/** GET /api/v1/tribot/topology/purdue-levels (gap DT-02). */
export interface TribotPurdueLevel {
  levelKey: string;
  numeric: number;
  displayLabel: string;
}

export interface TribotTopologyNode {
  nodeId: string;
  /**
   * hostname-or-ip. Beware: Tribot writes the literal string "Unknown" into
   * hostname for an unidentified device rather than leaving it null, so on a
   * real capture this is "Unknown" for most nodes. Read `ip` for the address
   * (gap DT-16) -- never parse this to find one.
   */
  label: string | null;
  deviceType: string | null;
  zoneId: string | null;
  zone?: TribotZone;

  // -- The fields Tribot's own topology asset card renders (gap DT-16) --
  ip: string | null;
  hostname: string | null;
  mac: string | null;
  vendor: string | null;
  manufacturer: string | null;
  riskScore: number | null;
  riskLevel: string | null;
  confidenceScore: number | null;
  protocols: string[];
  operationalCriticality: string | null;
  safetyImpact: string | null;
  cveCount: number;
  eolCount: number;
  /** "End of Support" when the asset has any EOL record, else "Supported". */
  lifecycle: string;
}

/**
 * One asset-to-asset conversation (gap DT-17) -- the aggregate of every raw
 * Communication row between a pair of assets, in both directions.
 *
 * This replaced the per-row link on `TribotTopology.links`. The per-row form
 * still exists at /topology/links as TribotTopologyLink below; it is the raw
 * view and is paginated over the Communication table, so it is not what a
 * graph should be drawn from.
 */
export interface TribotTopologyConversation {
  /** Direction-independent: A-to-B and B-to-A share one id. */
  conversationId: string;
  sourceNodeId: string;
  targetNodeId: string;
  sourceIp: string | null;
  targetIp: string | null;
  /** Every protocol observed between the pair, merged and sorted. */
  protocols: string[];
  packetCount: number;
  byteCount: number;
  /** How many raw Communication rows were folded into this conversation. */
  flowCount: number;
  /** True when traffic was seen in both directions, not just one. */
  bidirectional: boolean;
  firstSeen: string | null;
  lastSeen: string | null;
  sourceZoneId: string | null;
  targetZoneId: string | null;
}

/**
 * One raw Communication row, from /topology/links. Kept for that endpoint only
 * -- `TribotTopology.links` now carries TribotTopologyConversation instead.
 */
export interface TribotTopologyLink {
  linkId: string;
  sourceNodeId: string;
  targetNodeId: string;
  protocol: string | null;
  port: number | null;
  packetCount: number | null;
  byteCount: number | null;
  firstSeen: string | null;
  lastSeen: string | null;
  /** Gap DT-11 (partial). */
  sourceInterface: string | null;
  /** Both endpoints' zones, so cross-zone edges need no second lookup (DT-05). */
  sourceZoneId: string | null;
  targetZoneId: string | null;
}

export interface TribotTopology {
  nodes: TribotTopologyNode[];
  /** Aggregated conversations, not raw rows (gap DT-17). */
  links: TribotTopologyConversation[];
}

// ── Incident Response case status mirror (read-only) ──
//
// Tribot exposes case status only. Tasks, notes, observables, evidence and
// closure sign-off stay on its internal /api/ir/ surface by design, so USV can
// render the board and a case summary but never work a case (gap IR-03).

export type TribotCaseStatus =
  | 'New' | 'InProgress' | 'Contained' | 'ClosurePending' | 'Closed';

export interface TribotIrCase {
  caseId: string;
  caseNumber: string | null;
  title: string | null;
  summary: string | null;
  severity: string | null;
  status: TribotCaseStatus | string;
  pendingTier: string | null;
  creationSource: string | null;
  sourceIncidentId: string | null;
  sourceAlertId: string | null;
  assetId: string | null;
  assetIp: string | null;
  assetName: string | null;
  createdAt: string | null;
  updatedAt: string | null;
  closedAt: string | null;
}

export interface TribotIrBoardColumn {
  status: string;
  count: number;
}

export interface TribotIrBoardTier {
  tier: string;
  count: number;
}

/** GET /api/v1/tribot/ir-cases/board (gap IR-02). */
export interface TribotIrBoard {
  columns: TribotIrBoardColumn[];
  pendingOn: TribotIrBoardTier[];
  totalOpen: number;
  /** Open cases grouped by status. Closed is always empty by design. */
  cards: Record<string, TribotIrCase[]>;
}

export interface TribotApiError {
  error: {
    code: string;
    message: string;
  };
}
