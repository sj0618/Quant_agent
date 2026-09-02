import { useState } from "react";
import { Badge } from "../../components/common/Badge";
import { Card } from "../../components/common/Card";
import { ROUTES } from "../../config/routes";
import { BackendApiError } from "../../api/backendClient";
import { resendReportEmail } from "../../api/reportActionsClient";
import type { EmailDeliveryEntry, EmailDeliveryStatus } from "../../types/quantagent";

interface EmailHistoryTimelineProps {
  entries: EmailDeliveryEntry[];
}

const STATUS_LABELS: Record<EmailDeliveryStatus, string> = {
  sent: "전송 완료",
  resent: "재전송",
  failed: "전송 실패",
  draft: "발송 대기",
  submitted: "전송 접수",
  processing: "전송 처리 중",
  delivered: "수신 확인",
  cancelled: "발송 취소",
  unknown: "상태 미확인",
};

function statusVariant(status: EmailDeliveryStatus) {
  if (status === "failed" || status === "cancelled") {
    return "negative" as const;
  }
  if (status === "draft" || status === "submitted" || status === "processing" || status === "unknown") {
    return "neutral" as const;
  }
  return "info" as const;
}

function formatTimestamp(value: string | null) {
  if (!value) {
    return "시각 미기록";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("ko-KR", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}

function resendErrorMessage(error: unknown) {
  if (error instanceof BackendApiError) {
    if (error.status === 409 && error.code === "email_resend_unavailable") {
      return "지금은 재발송할 수 없는 상태입니다.";
    }
    if (error.status === 410) {
      return "이 리포트는 더 이상 재발송할 수 없습니다.";
    }
  }
  return "재발송 요청에 실패했습니다.";
}

export function EmailHistoryTimeline({ entries }: EmailHistoryTimelineProps) {
  const [resendState, setResendState] = useState<Record<string, "sending" | "sent" | string>>({});

  const handleResend = async (reportId: string, deliveryId: string) => {
    setResendState((current) => ({ ...current, [deliveryId]: "sending" }));
    try {
      await resendReportEmail(reportId);
      setResendState((current) => ({ ...current, [deliveryId]: "sent" }));
    } catch (error) {
      setResendState((current) => ({ ...current, [deliveryId]: resendErrorMessage(error) }));
    }
  };

  return (
    <div className="email-history-timeline">
      {entries.map((entry) => {
        const status = resendState[entry.deliveryId];
        return (
          <div className="email-history-item" key={entry.deliveryId}>
            <span className="email-history-item__dot" />
            <Card className="email-history-item__card">
              <div className="email-history-item__head">
                <div>
                  <Badge variant={statusVariant(entry.status)}>{STATUS_LABELS[entry.status]}</Badge>
                  <small>
                    {entry.reportDate ?? "날짜 미상"} · {formatTimestamp(entry.sentAt ?? entry.failedAt ?? entry.createdAt)}
                  </small>
                </div>
              </div>
              <strong className="email-history-item__strategy">{entry.strategyName ?? "전략 미상"}</strong>
              <p>{entry.reportTitle ?? "제목 없음"}</p>
              {entry.reportId ? (
                <div className="email-history-item__actions">
                  <a href={ROUTES.emailReportDetail(entry.reportId)}>이메일 리포트 보기</a>
                  <button
                    disabled={status === "sending"}
                    onClick={() => void handleResend(entry.reportId as string, entry.deliveryId)}
                    type="button"
                  >
                    다시 보내기
                  </button>
                  {status === "sent" ? <small>재발송 요청됨</small> : null}
                  {status && status !== "sending" && status !== "sent" ? <small>{status}</small> : null}
                </div>
              ) : null}
            </Card>
          </div>
        );
      })}
    </div>
  );
}
