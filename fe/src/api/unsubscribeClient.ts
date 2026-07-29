import { backendRequest } from "./backendClient";

export interface UnsubscribeInspection {
  status: "ready" | "already_unsubscribed";
  actionEmails: boolean;
}

export interface UnsubscribeResult {
  status: "unsubscribed" | "already_unsubscribed";
  actionEmails: false;
}

export function inspectUnsubscribeToken(token: string) {
  return backendRequest<UnsubscribeInspection>(`/unsubscribe?token=${encodeURIComponent(token)}`, { csrf: false });
}

export function confirmUnsubscribe(token: string) {
  return backendRequest<UnsubscribeResult>("/unsubscribe", {
    method: "POST",
    csrf: false,
    body: JSON.stringify({ token }),
  });
}
