import type { ReactNode } from "react";

interface AsyncStateProps {
  title: string;
  description?: string;
  tone?: "loading" | "empty" | "error";
  children?: ReactNode;
}

export function AsyncState({ title, description, tone = "empty", children }: AsyncStateProps) {
  return (
    <div className={`async-state async-state--${tone}`}>
      <div className="async-state__dot" />
      <div>
        <strong>{title}</strong>
        {description ? <p>{description}</p> : null}
        {children}
      </div>
    </div>
  );
}
