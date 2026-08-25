import type { NotificationSettings } from "../types/auth";
import { backendRequest } from "./backendClient";

const NOTIFICATION_SETTINGS_ENDPOINT = "/me/notifications";

export function getNotificationSettings(): Promise<NotificationSettings> {
  return backendRequest<NotificationSettings>(NOTIFICATION_SETTINGS_ENDPOINT);
}

export function saveNotificationSettings(settings: NotificationSettings): Promise<NotificationSettings> {
  return backendRequest<NotificationSettings>(NOTIFICATION_SETTINGS_ENDPOINT, {
    method: "PATCH",
    body: JSON.stringify(settings),
  });
}
