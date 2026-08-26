import { AppLayout } from "../components/layout/AppLayout";
import { StrategyWorkspace } from "../features/app/StrategyWorkspace";

export function AppPage() {
  return (
    <AppLayout active="workspace">
      <main className="reports-page">
        <StrategyWorkspace />
      </main>
    </AppLayout>
  );
}
