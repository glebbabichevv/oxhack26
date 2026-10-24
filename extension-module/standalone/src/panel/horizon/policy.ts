/**
 * Entry policy V3 (chosen on validation in the policy playoff): act only when the advantage after
 * costs is at least 1¢ per $1 share, and only from 24h before the scheduled end. Earlier than that
 * Horizon says "wait" and when. Kept apart from horizon.ts so the fee-aware model stays a file copy;
 * if a newer horizon.ts encodes the same rule itself, this stays consistent with it.
 */
import type { Decision } from './horizon';

export const MIN_NET_EDGE = 0.01;
export const ENTER_HOURS = 24;
export type Verdict = 'BET' | 'WAIT' | 'SKIP';

export function verdictOf(d: Decision): Verdict {
  if (d.action === 'NO_TRADE' || d.netEdge < MIN_NET_EDGE) return 'SKIP';
  return d.hours > ENTER_HOURS ? 'WAIT' : 'BET';
}
export const verdictRank: Record<Verdict, number> = { BET: 2, WAIT: 1, SKIP: 0 };
