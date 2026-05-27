import type { AdvisorPacket } from "../types";

/**
 * Lightweight client-side snapshot of the previous successful advisor packet.
 *
 * We keep only what we need to diff (no per-position arrays beyond first
 * actions) so the payload stays small and we never persist anything that
 * implies execution.
 */
export type PacketSnapshot = {
  packetHash: string;
  generatedAt: string;
  portfolioValue: number;
  riskIssueCount: number;
  firstAction: string;
  firstActionWeight: number;
  firstActionTarget: number;
  modelRoute: string;
  reasoningEffort: string;
  freshness: string;
  blockedActions: string[];
  policyVersion: string;
  policyName: string;
};

const STORAGE_KEY = "signal-prime:packet-history";

type StorageShape = {
  previous: PacketSnapshot | null;
  current: PacketSnapshot | null;
};

function readStorage(): StorageShape {
  if (typeof window === "undefined") return { previous: null, current: null };
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return { previous: null, current: null };
    const parsed = JSON.parse(raw) as Partial<StorageShape>;
    return {
      previous: parsed.previous ?? null,
      current: parsed.current ?? null,
    };
  } catch {
    return { previous: null, current: null };
  }
}

function writeStorage(value: StorageShape) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
  } catch {
    // ignore
  }
}

function freshnessSummary(packet: AdvisorPacket): string {
  const dataQuality = (packet.positions ?? []).reduce(
    (acc, pos) => {
      const freshness = (pos.dataQuality?.freshness ?? "missing").toLowerCase();
      acc[freshness] = (acc[freshness] ?? 0) + 1;
      return acc;
    },
    {} as Record<string, number>,
  );
  if (dataQuality.live && dataQuality.live > 0) return "live";
  if (dataQuality.recent && dataQuality.recent > 0) return "recent";
  if (dataQuality.partial && dataQuality.partial > 0) return "partial";
  if (dataQuality.stale && dataQuality.stale > 0) return "stale";
  if (dataQuality.sample && dataQuality.sample > 0) return "sample";
  return "missing";
}

export function packetToSnapshot(packet: AdvisorPacket): PacketSnapshot {
  const first = packet.recommendedPriority?.firstAction;
  return {
    packetHash: packet.packetHash ?? "",
    generatedAt: packet.generatedAt ?? "",
    portfolioValue: packet.portfolioValue ?? 0,
    riskIssueCount: packet.portfolioRisk?.issueCount ?? 0,
    firstAction: first ? `${first.action} ${first.symbol}` : "—",
    firstActionWeight: first?.currentWeight ?? 0,
    firstActionTarget: first?.targetWeight ?? 0,
    modelRoute:
      packet.decisionReceipt?.modelRoute ??
      packet.decisionReceipt?.model ??
      packet.audit?.modelRoute ??
      "—",
    reasoningEffort: packet.decisionReceipt?.reasoningEffort ?? "—",
    freshness: freshnessSummary(packet),
    blockedActions: packet.recommendedPriority?.blockedActions ?? [],
    policyVersion: packet.policyVersion ?? "",
    policyName: packet.decisionReceipt?.selectedPolicy ?? "",
  };
}

export function loadPreviousPacketSnapshot(currentHash?: string): PacketSnapshot | null {
  const history = readStorage();
  const candidate = history.previous;
  if (!candidate || !candidate.packetHash) return null;
  if (currentHash && candidate.packetHash === currentHash) return null;
  return candidate;
}

/**
 * Track the current packet. On every observed hash change we rotate the
 * existing "current" snapshot into "previous", and store the new snapshot as
 * "current". This means the Compare drawer always sees the *prior* run.
 */
export function savePacketSnapshot(packet: AdvisorPacket | null | undefined) {
  if (typeof window === "undefined" || !packet?.packetHash) return;
  const history = readStorage();
  const next = packetToSnapshot(packet);
  if (history.current?.packetHash === next.packetHash) return;
  writeStorage({
    previous: history.current ?? history.previous,
    current: next,
  });
}

export type PacketDiff = {
  portfolioValueChange: number;
  riskIssueChange: number;
  firstActionChanged: boolean;
  freshnessChanged: boolean;
  modelRouteChanged: boolean;
  newlyBlocked: string[];
  clearedBlocked: string[];
};

export function computePacketDiff(previous: PacketSnapshot, current: PacketSnapshot): PacketDiff {
  const previousBlocked = new Set(previous.blockedActions);
  const currentBlocked = new Set(current.blockedActions);
  return {
    portfolioValueChange: current.portfolioValue - previous.portfolioValue,
    riskIssueChange: current.riskIssueCount - previous.riskIssueCount,
    firstActionChanged: previous.firstAction !== current.firstAction,
    freshnessChanged: previous.freshness !== current.freshness,
    modelRouteChanged: previous.modelRoute !== current.modelRoute || previous.reasoningEffort !== current.reasoningEffort,
    newlyBlocked: Array.from(currentBlocked).filter((item) => !previousBlocked.has(item)),
    clearedBlocked: Array.from(previousBlocked).filter((item) => !currentBlocked.has(item)),
  };
}
