import type { HTMLAttributes, ReactNode } from "react";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  padded?: boolean;
}

export function Card({ children, className = "", padded = true, ...props }: CardProps) {
  return (
    <div className={["card", padded ? "card--padded" : "", className].filter(Boolean).join(" ")} {...props}>
      {children}
    </div>
  );
}
