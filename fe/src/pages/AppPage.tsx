import { AppLayout } from "../components/layout/AppLayout";
import { ResearchWorkspace } from "../features/research-contract/ResearchWorkspace";

export function AppPage() {
  return (
    <AppLayout active="workspace">
      <main className="reports-page">
        <ResearchWorkspace />
      </main>
    </AppLayout>
  );
}
