import type { ReactNode } from "react";

interface AsyncStateProps {
  title: string;
  description?: string;
  tone?: "loading" | "empty" | "error";
  pageHeading?: boolean;
  children?: ReactNode;
}

export function AsyncState({ title, description, tone = "empty", pageHeading = false, children }: AsyncStateProps) {
  return (
    <div className={`async-state async-state--${tone}`}>
      <div className="async-state__dot" />
      <div>
        {pageHeading ? <h1>{title}</h1> : <strong>{title}</strong>}
        {description ? <p>{description}</p> : null}
        {children}
      </div>
    </div>
  );
}
