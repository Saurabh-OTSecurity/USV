import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { DatePipe, KeyValuePipe } from '@angular/common';
import { forkJoin, of } from 'rxjs';
import { catchError } from 'rxjs/operators';

import { TribotService } from '../../../../shared/tribot.service';
import {
  TribotAlert,
  TribotPurdueLevel,
  TribotTopologyConversation,
  TribotTopologyNode,
  TribotZoneRosterEntry,
} from '../../../../shared/tribot.models';
import {
  COMM_STYLES,
  CommType,
  HIGH_FREQUENCY_PACKETS,
  PURDUE_TIERS,
  PurdueTier,
  UNCLASSIFIED_TIER,
  deviceColor,
  resolveTier,
} from '../../../../shared/purdue.util';

/**
 * Discovered topology, laid out the way Tribot's Digital Twin lays it out.
 *
 * Parity gaps DT-01, DT-04, DT-05, DT-06, DT-08, DT-12, DT-13, DT-14.
 * Previously this screen placed every node on a single circle by array index
 * and drew one undifferentiated grey line per link, which threw away the two
 * things the picture exists to show: which Purdue tier a device sits in, and
 * which conversations are abnormal.
 *
 * Still short of Tribot's own screen, deliberately and visibly:
 *   - no timeline scrubber (DT-07)
 *   - no baseline overlay, because the External Data API exposes none (DT-10)
 *   - node detail is a summary panel, not Tribot's eight-tab drawer (DT-09)
 * Those are stated in the template rather than silently absent.
 */
interface PositionedNode extends TribotTopologyNode {
  x: number;
  y: number;
  tier: PurdueTier;
  color: string;
  alertCount: number;
}

interface PositionedLink extends TribotTopologyConversation {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  commType: CommType;
  isCrossZone: boolean;
  isPolicyViolation: boolean;
}

interface TierLane {
  tier: PurdueTier;
  label: string;
  y: number;
  height: number;
  nodeCount: number;
}

type FilterId = 'all' | 'baseline' | 'new_comm' | 'high_frequency' | 'suspicious'
  | 'crosszone' | 'policy';

const FILTERS: { id: FilterId; label: string }[] = [
  { id: 'all', label: 'Show all' },
  { id: 'baseline', label: 'Baseline' },
  { id: 'new_comm', label: 'Cross-zone' },
  { id: 'high_frequency', label: 'High frequency' },
  { id: 'suspicious', label: 'Suspicious' },
  { id: 'crosszone', label: 'Cross-zone edges' },
  { id: 'policy', label: 'Policy violations' },
];

const CANVAS_WIDTH = 960;
const LANE_HEIGHT = 168;
const LANE_GAP = 10;
const NODE_W = 136;
const NODE_H = 56;

@Component({
  selector: 'app-tribot-topology',
  standalone: true,
  imports: [DatePipe, KeyValuePipe],
  templateUrl: './tribot-topology.component.html',
})
export class TribotTopologyComponent implements OnInit {
  private readonly tribotService = inject(TribotService);

  readonly nodes = signal<TribotTopologyNode[]>([]);
  readonly links = signal<TribotTopologyConversation[]>([]);
  readonly zones = signal<TribotZoneRosterEntry[]>([]);
  readonly tierLabels = signal<TribotPurdueLevel[]>([]);
  readonly alerts = signal<TribotAlert[]>([]);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);

  readonly selectedNodeId = signal<string | null>(null);
  readonly activeFilter = signal<FilterId>('all');
  readonly zoom = signal(1);
  readonly hoveredLink = signal<PositionedLink | null>(null);

  readonly filters = FILTERS;
  readonly commStyles = COMM_STYLES;
  readonly canvasWidth = CANVAS_WIDTH;
  readonly nodeWidth = NODE_W;
  readonly nodeHeight = NODE_H;

  /** Purdue level per zone name, from the zone roster (gap DT-15). */
  private readonly zoneLevels = computed<Record<string, number | null>>(() => {
    const map: Record<string, number | null> = {};
    for (const zone of this.zones()) map[zone.name] = zone.purdueLevel;
    return map;
  });

  /** Admin-edited tier labels (gap DT-02), falling back to our own defaults. */
  private readonly labelFor = computed<Record<string, string>>(() => {
    const map: Record<string, string> = {};
    for (const tier of PURDUE_TIERS) map[tier.key] = tier.defaultLabel;
    for (const row of this.tierLabels()) {
      // Tribot seeds each tier's display_label to the tier key itself, so an
      // un-renamed tier comes back as bare "L2". Keep our fuller label in that
      // case and defer only to a genuine admin rename.
      if (row.displayLabel && row.displayLabel !== row.levelKey) {
        map[row.levelKey] = row.displayLabel;
      }
    }
    return map;
  });

  /** Alert count per asset, so a node can show it carries alerts (gap DT-12). */
  private readonly alertsByAsset = computed<Record<string, number>>(() => {
    const counts: Record<string, number> = {};
    for (const alert of this.alerts()) {
      if (alert.assetId) counts[alert.assetId] = (counts[alert.assetId] || 0) + 1;
    }
    return counts;
  });

  /** Endpoint pairs named by an alert, for the suspicious-edge rule. */
  private readonly alertedPairs = computed<Set<string>>(() => {
    const pairs = new Set<string>();
    for (const alert of this.alerts()) {
      if (alert.source && alert.destination) {
        pairs.add([alert.source, alert.destination].sort().join('|'));
      }
    }
    return pairs;
  });

  /**
   * Tier swim lanes, ordered L4 at the top down to L1 at the bottom -- the
   * orientation every Purdue diagram uses, and the one Tribot's own screen
   * uses. Only tiers that actually hold a node get a lane, so a small plant
   * does not render four empty bands.
   */
  readonly lanes = computed<TierLane[]>(() => {
    const counts = new Map<string, number>();
    for (const node of this.nodes()) {
      const tier = this.tierForNode(node);
      counts.set(tier.key, (counts.get(tier.key) || 0) + 1);
    }
    // L4 at the top down to L1, then Unclassified last so unresolved devices
    // sit below the plant rather than inside it.
    const present = PURDUE_TIERS.filter((t) => counts.has(t.key));
    const ordered = [...present].reverse();
    if (counts.has(UNCLASSIFIED_TIER.key)) ordered.push(UNCLASSIFIED_TIER);
    return ordered.map((tier, index) => ({
      tier,
      label: this.labelFor()[tier.key] || tier.defaultLabel,
      y: index * (LANE_HEIGHT + LANE_GAP),
      height: LANE_HEIGHT,
      nodeCount: counts.get(tier.key) || 0,
    }));
  });

  readonly canvasHeight = computed(
    () => Math.max(1, this.lanes().length) * (LANE_HEIGHT + LANE_GAP),
  );

  readonly positionedNodes = computed<PositionedNode[]>(() => {
    const laneByKey = new Map(this.lanes().map((lane) => [lane.tier.key, lane]));
    const placedPerLane = new Map<string, number>();
    const alertCounts = this.alertsByAsset();

    return this.nodes().map((node) => {
      const tier = this.tierForNode(node);
      const lane = laneByKey.get(tier.key);
      const laneY = lane ? lane.y : 0;
      const indexInLane = placedPerLane.get(tier.key) || 0;
      placedPerLane.set(tier.key, indexInLane + 1);

      // Laid out left-to-right inside the lane, wrapping when a tier is
      // crowded. Tribot persists operator-arranged canvas positions (gap
      // DT-03), but those live on the asset, not on the topology node shape,
      // so this deterministic placement is the fallback until the node shape
      // carries them.
      const perRow = Math.max(1, Math.floor((CANVAS_WIDTH - 24) / (NODE_W + 12)));
      const column = indexInLane % perRow;
      const row = Math.floor(indexInLane / perRow);

      return {
        ...node,
        tier,
        x: 16 + column * (NODE_W + 12),
        y: laneY + 32 + row * (NODE_H + 8),
        color: node.zone?.color || deviceColor(node.deviceType),
        alertCount: node.nodeId ? alertCounts[node.nodeId] || 0 : 0,
      };
    });
  });

  readonly positionedLinks = computed<PositionedLink[]>(() => {
    const byId = new Map(this.positionedNodes().map((n) => [n.nodeId, n]));
    const alerted = this.alertedPairs();
    const levels = this.zoneLevels();

    const positioned: PositionedLink[] = [];
    for (const link of this.links()) {
      const source = byId.get(link.sourceNodeId);
      const target = byId.get(link.targetNodeId);
      if (!source || !target) continue;

      const isCrossZone = !!link.sourceZoneId && !!link.targetZoneId
        && link.sourceZoneId !== link.targetZoneId;

      // Tribot's rule: a hop spanning more than one Purdue level is a policy
      // violation. Both endpoints' zone ids now arrive on the link (DT-11), so
      // this needs no second lookup.
      const sourceLevel = link.sourceZoneId ? levels[link.sourceZoneId] : null;
      const targetLevel = link.targetZoneId ? levels[link.targetZoneId] : null;
      const isPolicyViolation = sourceLevel !== null && sourceLevel !== undefined
        && targetLevel !== null && targetLevel !== undefined
        && Math.abs(sourceLevel - targetLevel) > 1;

      // Correlate on IP, which every node now carries (gap DT-16). This used
      // to key off `label`, which is the literal string "Unknown" for most
      // nodes on a real capture -- so every unidentified device collided into
      // one key and suspicious-edge detection was meaningless.
      const pairKey = [link.sourceIp ?? '', link.targetIp ?? ''].sort().join('|');
      const isSuspicious = alerted.has(pairKey);

      let commType: CommType = 'baseline';
      if (isSuspicious || isPolicyViolation) commType = 'suspicious';
      else if ((link.packetCount ?? 0) > HIGH_FREQUENCY_PACKETS) commType = 'high_frequency';
      else if (isCrossZone) commType = 'new_comm';

      positioned.push({
        ...link,
        x1: source.x + NODE_W / 2,
        y1: source.y + NODE_H / 2,
        x2: target.x + NODE_W / 2,
        y2: target.y + NODE_H / 2,
        commType,
        isCrossZone,
        isPolicyViolation,
      });
    }
    return positioned;
  });

  readonly totalFlows = computed(() =>
    this.positionedLinks().reduce((sum, l) => sum + (l.flowCount || 0), 0));

  readonly visibleLinks = computed<PositionedLink[]>(() => {
    const filter = this.activeFilter();
    const selected = this.selectedNodeId();
    let links = this.positionedLinks();

    if (filter === 'crosszone') links = links.filter((l) => l.isCrossZone);
    else if (filter === 'policy') links = links.filter((l) => l.isPolicyViolation);
    else if (filter !== 'all') links = links.filter((l) => l.commType === filter);

    if (selected) {
      links = links.filter((l) => l.sourceNodeId === selected || l.targetNodeId === selected);
    }
    return links;
  });

  readonly commCounts = computed<Record<string, number>>(() => {
    const counts: Record<string, number> = {
      baseline: 0, new_comm: 0, high_frequency: 0, suspicious: 0,
      crossZone: 0, policyViolation: 0,
    };
    for (const link of this.positionedLinks()) {
      counts[link.commType] += 1;
      if (link.isCrossZone) counts['crossZone'] += 1;
      if (link.isPolicyViolation) counts['policyViolation'] += 1;
    }
    return counts;
  });

  readonly selectedNode = computed<PositionedNode | null>(() => {
    const id = this.selectedNodeId();
    return id ? this.positionedNodes().find((n) => n.nodeId === id) ?? null : null;
  });

  readonly selectedNodeLinks = computed<PositionedLink[]>(() => {
    const id = this.selectedNodeId();
    if (!id) return [];
    return this.positionedLinks().filter((l) => l.sourceNodeId === id || l.targetNodeId === id);
  });

  ngOnInit(): void {
    // Zones, tier labels and alerts are enrichment: a failure in any of them
    // degrades the picture (default labels, unclassified edges) rather than
    // blanking a screen whose core data loaded fine.
    forkJoin({
      topology: this.tribotService.getTopology(300),
      zones: this.tribotService.listTopologyZones().pipe(catchError(() => of(null))),
      tiers: this.tribotService.listPurdueLevels().pipe(catchError(() => of(null))),
      alerts: this.tribotService.listAlerts({ pageSize: 200 }).pipe(catchError(() => of(null))),
    }).subscribe({
      next: ({ topology, zones, tiers, alerts }) => {
        this.nodes.set(topology.data.nodes);
        this.links.set(topology.data.links);
        if (zones) this.zones.set(zones.data);
        if (tiers) this.tierLabels.set(tiers.data);
        if (alerts) this.alerts.set(alerts.data);
        this.loading.set(false);
      },
      error: (err) => {
        this.error.set(this.describeError(err));
        this.loading.set(false);
      },
    });
  }

  private tierForNode(node: TribotTopologyNode): PurdueTier {
    const zoneLevel = node.zoneId ? this.zoneLevels()[node.zoneId] : null;
    return resolveTier(zoneLevel, node.deviceType);
  }

  setFilter(id: FilterId): void {
    this.activeFilter.set(id);
  }

  selectNode(nodeId: string): void {
    this.selectedNodeId.set(this.selectedNodeId() === nodeId ? null : nodeId);
  }

  clearSelection(): void {
    this.selectedNodeId.set(null);
  }

  zoomIn(): void {
    this.zoom.set(Math.min(this.zoom() + 0.2, 2.5));
  }

  zoomOut(): void {
    this.zoom.set(Math.max(this.zoom() - 0.2, 0.5));
  }

  resetView(): void {
    this.zoom.set(1);
    this.activeFilter.set('all');
    this.selectedNodeId.set(null);
  }

  isFaded(node: PositionedNode): boolean {
    const selected = this.selectedNodeId();
    if (!selected) return false;
    if (node.nodeId === selected) return false;
    return !this.selectedNodeLinks().some(
      (l) => l.sourceNodeId === node.nodeId || l.targetNodeId === node.nodeId,
    );
  }

  nodeLabel(nodeId: string): string {
    return this.positionedNodes().find((n) => n.nodeId === nodeId)?.label || nodeId;
  }

  styleFor(commType: CommType) {
    return COMM_STYLES[commType];
  }

  /** Risk band colour, mirroring Tribot's getRiskColor thresholds. */
  riskColor(score: number | null): string {
    const value = score ?? 0;
    if (value >= 75) return '#c0392b';
    if (value >= 50) return '#d0973a';
    if (value >= 25) return '#eab308';
    return '#3fb96c';
  }

  /** First two protocols, as Tribot's card does. */
  topProtocols(node: PositionedNode): string[] {
    return (node.protocols || []).slice(0, 2);
  }

  showLinkTooltip(link: PositionedLink): void {
    this.hoveredLink.set(link);
  }

  hideLinkTooltip(): void {
    this.hoveredLink.set(null);
  }

  private describeError(err: unknown): string {
    const apiError = (err as { error?: { error?: { code?: string; message?: string } } })?.error?.error;
    if (apiError?.code === 'TRIBOT_NOT_CONFIGURED') {
      return 'Tribot is not configured for this USV instance (set TRIBOT_BASE_URL / TRIBOT_API_TOKEN in the backend).';
    }
    return apiError?.message || 'Unable to load topology data from Tribot.';
  }
}
