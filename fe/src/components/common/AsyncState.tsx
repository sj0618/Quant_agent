import type { ReactNode } from "react";

interface AsyncStateProps {
  title: string;
  description?: string;
  tone?: "loading" | "empty" | "error";
  pageHeading?: boolean;
  className?: string;
  children?: ReactNode;
}

export function AsyncState({
  title,
  description,
  tone = "empty",
  pageHeading = false,
  className,
  children,
}: AsyncStateProps) {
  return (
    <div className={`async-state async-state--${tone}${className ? ` ${className}` : ""}`}>
      <div className="async-state__dot" />
      <div>
        {pageHeading ? <h1>{title}</h1> : <strong>{title}</strong>}
        {description ? <p>{description}</p> : null}
        {children}
      </div>
    </div>
  );
}
