import { Badge } from "../../components/common/Badge";
import { Card } from "../../components/common/Card";
import { ROUTES } from "../../config/routes";
import type { EmailDigestHistoryEntry } from "../../types/quantagent";

interface EmailHistoryTimelineProps {
  entries: EmailDigestHistoryEntry[];
}

function statusVariant(status: EmailDigestHistoryEntry["status"]) {
  if (status === "failed") {
    return "negative";
  }
  return "info";
}

function statusLabel(status: EmailDigestHistoryEntry["status"]) {
  if (status === "failed") {
    return "전송 실패";
  }
  if (status === "resent") {
    return "재전송";
  }
  if (status === "draft") {
    return "초안";
  }
  return "전송 완료";
}

export function EmailHistoryTimeline({ entries }: EmailHistoryTimelineProps) {
  return (
    <div className="email-history-timeline">
      {entries.map((entry) => (
        <div className="email-history-item" key={entry.id}>
          <span className="email-history-item__dot" />
          <Card className="email-history-item__card">
            <div className="email-history-item__head">
              <div>
                <Badge variant={statusVariant(entry.status)}>{statusLabel(entry.status)}</Badge>
                <small>{entry.reportDate} · {entry.sentAt}</small>
              </div>
            </div>
            <strong className="email-history-item__strategy">{entry.strategyName}</strong>
            <p>{entry.title}</p>
            <div className="email-history-item__actions">
              <a href={ROUTES.reportDetail(entry.reportId)}>이메일 원문 보기</a>
            </div>
          </Card>
        </div>
      ))}
    </div>
  );
}
