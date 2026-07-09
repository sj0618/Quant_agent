import type { ReactNode } from "react";
import { TopBar } from "./TopBar";

interface AppLayoutProps {
  active: "workspace" | "reports" | "profile" | "search";
  children: ReactNode;
}

export function AppLayout({ active, children }: AppLayoutProps) {
  return (
    <div className="app-shell">
      <TopBar active={active} />
      {children}
    </div>
  );
}
