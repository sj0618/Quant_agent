import type { ReactNode } from "react";
import type { SignalType, Tone } from "../../types/quantagent";

type BadgeVariant = Tone | "dark" | "soft" | "signal";

interface BadgeProps {
  children: ReactNode;
  variant?: BadgeVariant;
  signal?: SignalType;
  className?: string;
}

export function Badge({ children, variant = "soft", signal, className = "" }: BadgeProps) {
  const classes = ["badge", `badge--${signal ? signal.toLowerCase() : variant}`, className].filter(Boolean).join(" ");

  return <span className={classes}>{children}</span>;
}
