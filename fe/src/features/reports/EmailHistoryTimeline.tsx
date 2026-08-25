import { Badge } from "../../components/common/Badge";
import { Card } from "../../components/common/Card";
import { ROUTES } from "../../config/routes";
import type { EmailDeliveryEntry, EmailDeliveryStatus } from "../../types/quantagent";

interface EmailHistoryTimelineProps {
  entries: EmailDeliveryEntry[];
}

const STATUS_LABELS: Record<EmailDeliveryStatus, string> = {
  sent: "전송 완료",
  resent: "재전송",
  failed: "전송 실패",
  draft: "발송 대기",
};

function statusVariant(status: EmailDeliveryStatus) {
  if (status === "failed") {
    return "negative" as const;
  }
  if (status === "draft") {
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

export function EmailHistoryTimeline({ entries }: EmailHistoryTimelineProps) {
  return (
    <div className="email-history-timeline">
      {entries.map((entry) => (
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
                <a href={ROUTES.reportDetail(entry.reportId)}>리포트 보기</a>
              </div>
            ) : null}
          </Card>
        </div>
      ))}
    </div>
  );
}
