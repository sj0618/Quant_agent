import { backendRequest } from "./backendClient";
import type { EmailDeliveryEntry, EmailDeliveryStatus } from "../types/quantagent";

interface EmailDeliveryListResponse {
  items: Array<Partial<EmailDeliveryEntry> & { deliveryId?: string }>;
  meta?: { limit?: number; hasMore?: boolean; nextCursor?: string | null };
}

const KNOWN_STATUSES: EmailDeliveryStatus[] = ["sent", "resent", "failed", "draft"];

function normalizeStatus(status: string | undefined): EmailDeliveryStatus {
  const normalized = (status ?? "").toLowerCase();
  return KNOWN_STATUSES.includes(normalized as EmailDeliveryStatus)
    ? (normalized as EmailDeliveryStatus)
    : "draft";
}

/** Recent report emails for the signed-in user, newest first.
 *
 * `GET /api/v1/me/email-deliveries` has been live all along; its only consumer was
 * deleted in `6dadc69` along with the timeline UI, leaving the endpoint orphaned.
 */
export async function getEmailDeliveries(limit = 10): Promise<EmailDeliveryEntry[]> {
  const response = await backendRequest<EmailDeliveryListResponse>(
    `/me/email-deliveries?${new URLSearchParams({ limit: String(limit) }).toString()}`,
  );
  const items = Array.isArray(response?.items) ? response.items : [];
  return items.map((item) => ({
    deliveryId: item.deliveryId ?? "",
    reportId: item.reportId ?? null,
    reportTitle: item.reportTitle ?? null,
    strategyName: item.strategyName ?? null,
    status: normalizeStatus(item.status),
    reportDate: item.reportDate ?? null,
    sentAt: item.sentAt ?? null,
    createdAt: item.createdAt ?? null,
    failedAt: item.failedAt ?? null,
  }));
}
