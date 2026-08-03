export interface AuthUser {
  id: string;
  name: string;
  email: string;
  provider: "google";
  avatarUrl?: string;
}

export interface AuthSession {
  user: AuthUser;
  accessToken?: string;
  expiresAt?: string;
  /** Epoch ms of the last successful `/auth/me`. Lets a fresh session skip revalidation. */
  validatedAt?: number;
}

export interface NotificationSettings {
  dailyReportEmail: boolean;
  email: string;
  actionEmails?: boolean;
  marketingEmail?: boolean;
  deliveryHour?: string;
}
