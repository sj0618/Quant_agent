import { useEffect, useState } from "react";
import { Badge } from "../components/common/Badge";
import { Button } from "../components/common/Button";
import { Card } from "../components/common/Card";
import { AppLayout } from "../components/layout/AppLayout";
import { getCurrentSession, signOut } from "../api/authClient";
import { getNotificationSettings, saveNotificationSettings } from "../api/preferencesClient";
import { getEmailDeliveries } from "../api/emailDeliveryClient";
import { EmailHistoryTimeline } from "../features/reports/EmailHistoryTimeline";
import { ROUTES } from "../config/routes";
import type { NotificationSettings } from "../types/auth";
import type { EmailDeliveryEntry } from "../types/quantagent";

interface ProfilePageProps {
  initialTab: "profile" | "notifications";
}

export function ProfilePage({ initialTab }: ProfilePageProps) {
  const session = getCurrentSession();
  const [activeTab, setActiveTab] = useState(initialTab);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [settings, setSettings] = useState<NotificationSettings | null>(null);
  const [settingsLoading, setSettingsLoading] = useState(false);
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [deliveries, setDeliveries] = useState<EmailDeliveryEntry[] | null>(null);
  const [deliveriesError, setDeliveriesError] = useState<string | null>(null);

  // The send history is informational: a failure here must not take the settings form
  // down with it, so it keeps its own error slot instead of the page-level banner.
  useEffect(() => {
    if (!session) {
      return;
    }
    let cancelled = false;
    getEmailDeliveries()
      .then((entries) => {
        if (!cancelled) {
          setDeliveries(entries);
        }
      })
      .catch((deliveryError: unknown) => {
        if (!cancelled) {
          setDeliveries([]);
          setDeliveriesError(
            deliveryError instanceof Error ? deliveryError.message : "이메일 발송 이력을 불러오지 못했습니다.",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [session?.user.id]);

  useEffect(() => {
    if (!session) {
      return;
    }

    let cancelled = false;
    setSettingsLoading(true);
    getNotificationSettings()
      .then((nextSettings) => {
        if (!cancelled) {
          setSettings(nextSettings);
        }
      })
      .catch((settingsError: unknown) => {
        if (!cancelled) {
          setError(settingsError instanceof Error ? settingsError.message : "알림 설정을 불러오지 못했습니다.");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setSettingsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [session?.user.id]);

  if (!session) {
    return null;
  }
  const providerLabel = session.user.provider === "google" ? "Google 계정" : session.user.provider;

  const handleSaveSettings = async () => {
    if (!settings) {
      return;
    }
    setError(null);
    setStatus(null);
    setSettingsSaving(true);
    try {
      const savedSettings = await saveNotificationSettings(settings);
      setSettings(savedSettings);
      setStatus("알림 설정을 저장했습니다.");
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "알림 설정 저장에 실패했습니다.");
    } finally {
      setSettingsSaving(false);
    }
  };

  const updateNotificationSettings = (recipe: (current: NotificationSettings) => NotificationSettings) => {
    setSettings((current) => (current ? recipe(current) : current));
  };

  const handleSignOut = async () => {
    setError(null);
    setStatus(null);
    try {
      await signOut();
      window.location.assign(ROUTES.home);
    } catch (signOutError) {
      setError(signOutError instanceof Error ? signOutError.message : "로그아웃에 실패했습니다.");
    }
  };

  return (
    <AppLayout active="profile">
      <main className="settings-page">
        <div className="settings-page__head">
          <div>
            <Badge variant="dark">MY PAGE</Badge>
            <h1>마이페이지</h1>
            <p>Google 계정과 Daily 리포트 수신 설정을 관리합니다.</p>
          </div>
          <Button onClick={handleSignOut} variant="secondary">로그아웃</Button>
        </div>

        <div className="settings-tabs">
          <a className={activeTab === "profile" ? "is-active" : ""} href={ROUTES.me} onClick={() => setActiveTab("profile")}>프로필</a>
          <a
            className={activeTab === "notifications" ? "is-active" : ""}
            href={ROUTES.notifications}
            onClick={() => setActiveTab("notifications")}
          >
            알림 설정
          </a>
        </div>

        {status ? <div className="status-banner status-banner--success"><strong>{status}</strong></div> : null}
        {error ? <div className="status-banner status-banner--error"><strong>{error}</strong></div> : null}

        {activeTab === "profile" ? (
          <Card className="settings-card">
            <div className="profile-row">
              <span className="avatar avatar--large" />
              <div>
                <h2>{session.user.name}</h2>
                <p>{session.user.email}</p>
                <Badge variant="info">{providerLabel}</Badge>
              </div>
            </div>
          </Card>
        ) : settingsLoading || !settings ? (
          <Card className="settings-card">
            <p>{settingsLoading ? "알림 설정을 서버에서 불러오는 중입니다." : "알림 설정을 불러오지 못했습니다."}</p>
          </Card>
        ) : (
          <Card className="settings-card">
            <div className="form-grid">
              <label className="field">
                <span>리포트 수신 이메일</span>
                <input
                  onChange={(event) => updateNotificationSettings((current) => ({ ...current, email: event.target.value }))}
                  value={settings.email}
                />
              </label>
              <label className="field">
                <span>발송 시간</span>
                <select
                  onChange={(event) => updateNotificationSettings((current) => ({ ...current, deliveryHour: event.target.value }))}
                  value={settings.deliveryHour}
                >
                  <option value="08:00">08:00</option>
                  <option value="09:00">09:00</option>
                  <option value="18:00">18:00</option>
                </select>
              </label>
            </div>
            <label className="toggle-row">
              <input
                checked={settings.dailyReportEmail}
                onChange={(event) => updateNotificationSettings((current) => ({ ...current, dailyReportEmail: event.target.checked }))}
                type="checkbox"
              />
              <span>Daily 리포트 이메일 수신</span>
            </label>
            <label className="toggle-row">
              <input
                checked={settings.actionEmails}
                onChange={(event) => updateNotificationSettings((current) => ({ ...current, actionEmails: event.target.checked }))}
                type="checkbox"
              />
              <span>공유 링크 관련 처리 결과 이메일 수신</span>
            </label>
            <label className="toggle-row">
              <input
                checked={settings.marketingEmail}
                onChange={(event) => updateNotificationSettings((current) => ({ ...current, marketingEmail: event.target.checked }))}
                type="checkbox"
              />
              <span>서비스 업데이트 수신</span>
            </label>
            <div className="form-actions">
              <Button disabled={settingsSaving} onClick={handleSaveSettings} variant="dark">
                {settingsSaving ? "저장 중" : "설정 저장"}
              </Button>
            </div>
          </Card>
        )}

        <Card className="settings-card">
          <div className="settings-card__head">
            <div>
              <Badge variant="soft">발송 이력</Badge>
              <h2>이메일 발송 타임라인</h2>
              <p>전송 완료, 실패, 재전송 이력을 최근 순서대로 확인합니다.</p>
            </div>
          </div>
          {deliveriesError ? (
            <p className="settings-card__inline-copy settings-card__inline-copy--error">{deliveriesError}</p>
          ) : deliveries === null ? (
            <p className="settings-card__inline-copy">이메일 발송 이력을 불러오는 중입니다.</p>
          ) : deliveries.length === 0 ? (
            <p className="settings-card__inline-copy">아직 발송된 리포트 이메일이 없습니다.</p>
          ) : (
            <EmailHistoryTimeline entries={deliveries} />
          )}
        </Card>
      </main>
    </AppLayout>
  );
}
