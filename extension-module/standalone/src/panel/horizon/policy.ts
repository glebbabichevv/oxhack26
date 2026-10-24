/**
 * Entry policy V3 lives in horizon.ts now (decide() reads model.json's policy: advantage after
 * costs >= 1¢, enter only within 24h of the end). An early market comes back as NO_TRADE with
 * wait: true and wouldBe = the action it will be. These are thin readers of that decision.
 */
import type { Action, Decision } from './horizon';

export type Verdict = 'BET' | 'WAIT' | 'SKIP';

export function verdictOf(d: Decision): Verdict {
  if (d.wait && d.wouldBe) return 'WAIT';
  return d.action === 'NO_TRADE' ? 'SKIP' : 'BET';
}
/** The side Horizon backs now, or will back once the window opens. */
export const intendedAction = (d: Decision): Action => (d.action !== 'NO_TRADE' ? d.action : d.wait && d.wouldBe ? d.wouldBe : 'NO_TRADE');
export const verdictRank: Record<Verdict, number> = { BET: 2, WAIT: 1, SKIP: 0 };
