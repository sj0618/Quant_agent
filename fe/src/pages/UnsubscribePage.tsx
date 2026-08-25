import { useEffect, useState } from "react";
import { BackendApiError } from "../api/backendClient";
import { confirmUnsubscribe, inspectUnsubscribeToken } from "../api/unsubscribeClient";
import { Badge } from "../components/common/Badge";
import { Button } from "../components/common/Button";
import { Card } from "../components/common/Card";
import { Footer } from "../components/layout/Footer";
import { ROUTES } from "../config/routes";

type UnsubscribeViewState = "loading" | "ready" | "already" | "invalid" | "expired" | "disabled" | "unavailable" | "success" | "error";

function classifyError(error: unknown): UnsubscribeViewState {
  if (!(error instanceof BackendApiError)) return "unavailable";
  if (error.code === "unsubscribe_token_expired") return "expired";
  if (["unsubscribe_disabled", "unsubscribe_secret_missing", "unsubscribe_base_url_missing"].includes(error.code)) return "disabled";
  if (["unsubscribe_token_required", "unsubscribe_token_malformed", "unsubscribe_token_invalid", "unsubscribe_target_invalid"].includes(error.code)) return "invalid";
  return error.status >= 500 ? "unavailable" : "error";
}

const COPY: Record<UnsubscribeViewState, string> = {
  loading: "수신 거부 링크를 확인하고 있습니다.",
  ready: "이 링크로 리포트 이메일 수신을 중단할 수 있습니다.",
  already: "이미 리포트 이메일 수신이 해제되어 있습니다.",
  invalid: "유효하지 않은 수신 거부 링크입니다.",
  expired: "수신 거부 링크가 만료되었습니다.",
  disabled: "현재 수신 거부 기능이 비활성화되어 있습니다.",
  unavailable: "현재 수신 거부 상태를 확인할 수 없습니다. 잠시 후 다시 시도해 주세요.",
  success: "리포트 이메일 수신을 해제했습니다.",
  error: "수신 거부 요청을 처리하지 못했습니다.",
};

export function UnsubscribePage() {
  const token = new URLSearchParams(window.location.search).get("token") ?? "";
  const [viewState, setViewState] = useState<UnsubscribeViewState>("loading");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (!token) {
      setViewState("invalid");
      return () => { cancelled = true; };
    }
    inspectUnsubscribeToken(token)
      .then((result) => {
        if (!cancelled) setViewState(result.status === "already_unsubscribed" ? "already" : "ready");
      })
      .catch((error: unknown) => {
        if (!cancelled) setViewState(classifyError(error));
      });
    return () => { cancelled = true; };
  }, [token]);

  const handleConfirm = async () => {
    setSubmitting(true);
    try {
      const result = await confirmUnsubscribe(token);
      setViewState(result.status === "already_unsubscribed" ? "already" : "success");
    } catch (error) {
      setViewState(classifyError(error));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="landing-page">
      <nav className="landing-nav">
        <a className="brand" href={ROUTES.home}><span className="brand__mark" /><span>QuantAgent</span></a>
      </nav>
      <section className="legal-page">
        <Badge variant="dark">EMAIL</Badge>
        <h1>수신 거부</h1>
        <Card className="auth-panel">
          <p>{COPY[viewState]}</p>
          {viewState === "ready" ? (
            <div className="form-actions">
              <Button disabled={submitting} onClick={() => void handleConfirm()} variant="dark">
                {submitting ? "처리 중" : "수신 거부 확인"}
              </Button>
            </div>
          ) : null}
          {["invalid", "expired", "disabled", "unavailable", "error"].includes(viewState) ? (
            <div className="status-banner status-banner--error"><strong>{COPY[viewState]}</strong></div>
          ) : null}
          {["already", "success"].includes(viewState) ? (
            <div className="status-banner status-banner--success"><strong>{COPY[viewState]}</strong></div>
          ) : null}
        </Card>
      </section>
      <Footer />
    </main>
  );
}
