import { useState } from "react";
import { AsyncState } from "../components/common/AsyncState";
import { AppLayout } from "../components/layout/AppLayout";
import { getReportById } from "../api/quantAgentClient";
import { copyReportShareLink, printCurrentView, resendReportEmail } from "../api/reportActionsClient";
import { ROUTES } from "../config/routes";
import { ReportDetail } from "../features/reports/ReportDetail";
import { useAsyncData } from "../hooks/useAsyncData";

interface ReportDetailPageProps {
  id: string;
}

export function ReportDetailPage({ id }: ReportDetailPageProps) {
  const { data, loading, error } = useAsyncData(() => getReportById(id), [id]);
  const [actionStatus, setActionStatus] = useState<string | null>(null);

  const handleAction = async (action: "resend" | "pdf" | "share") => {
    setActionStatus(null);
    try {
      if (action === "pdf") {
        printCurrentView();
        setActionStatus("브라우저 인쇄 대화상자에서 PDF로 저장할 수 있습니다.");
      }

      if (action === "share") {
        const url = await copyReportShareLink(id);
        setActionStatus(`공유 링크를 복사했습니다: ${url}`);
      }

      if (action === "resend") {
        await resendReportEmail(id);
        setActionStatus("리포트 이메일 재발송을 요청했습니다.");
      }
    } catch (actionError) {
      setActionStatus(actionError instanceof Error ? actionError.message : "리포트 액션 처리에 실패했습니다.");
    }
  };

  if (loading) {
    return <AsyncState title="리포트 상세를 불러오는 중입니다" tone="loading" />;
  }

  if (error) {
    return <AsyncState title="리포트 상세를 불러오지 못했습니다" description={error.message} tone="error" />;
  }

  if (!data) {
    return <AsyncState title="리포트를 찾을 수 없습니다" description="요청한 리포트 ID에 해당하는 분석 API 결과가 없습니다." tone="empty" />;
  }

  return (
    <AppLayout active="reports">
      <div className="report-subbar">
        <a href={ROUTES.reports}>← 전략 레포트 목록</a>
        {data.strategyId ? (
          <>
            <span>/</span>
            <a href={ROUTES.strategyReportDetail(data.strategyId)}>{data.strategyName}</a>
          </>
        ) : null}
        <span>/</span>
        <strong>{data.date}</strong>
        <div>
          <button onClick={() => handleAction("resend")} type="button">이메일 재발송</button>
          <button onClick={() => handleAction("pdf")} type="button">PDF 저장</button>
          <button onClick={() => handleAction("share")} type="button">공유 링크</button>
        </div>
      </div>
      {actionStatus ? <div className="action-feedback action-feedback--subbar">{actionStatus}</div> : null}
      <ReportDetail report={data} />
    </AppLayout>
  );
}
