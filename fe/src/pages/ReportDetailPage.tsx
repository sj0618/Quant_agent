import { EmailReportDetailPage } from "./EmailReportDetailPage";

interface ReportDetailPageProps {
  id: string;
}

export function ReportDetailPage({ id }: ReportDetailPageProps) {
  // Kept as a source-compatible entry point for an older import.  No live route
  // uses it: email reports now live exclusively below `/me/email-reports/:id`.
  return <EmailReportDetailPage id={id} />;
}
