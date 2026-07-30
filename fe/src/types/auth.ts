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
}

export interface NotificationSettings {
  dailyReportEmail: boolean;
  email: string;
  actionEmails?: boolean;
  marketingEmail?: boolean;
  deliveryHour?: string;
}
