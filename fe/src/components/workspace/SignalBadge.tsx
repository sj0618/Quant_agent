import type { SignalAction } from "../../types/quantagent";

const ACTION_LABEL: Record<SignalAction, string> = {
  BUY: "BUY",
  SELL: "SELL",
  HOLD: "HOLD",
  WATCH: "WATCH",
  FILTERED_OUT: "FILTERED OUT",
};

export function SignalBadge({ action, compact = false }: { action: SignalAction; compact?: boolean }) {
  return (
    <span className={`signal-badge signal-badge--${action.toLowerCase()} ${compact ? "signal-badge--compact" : ""}`}>
      {ACTION_LABEL[action]}
    </span>
  );
}
