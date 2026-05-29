import { useState, type FormEvent } from "react";
import { Badge } from "../components/common/Badge";
import { Button } from "../components/common/Button";
import { Card } from "../components/common/Card";
import { Footer } from "../components/layout/Footer";
import { disableDailyReportEmail } from "../api/preferencesClient";
import { ROUTES } from "../config/routes";

export function UnsubscribePage() {
  const params = new URLSearchParams(window.location.search);
  const [email, setEmail] = useState(params.get("email") ?? "");
  const [status, setStatus] = useState<string | null>(null);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    disableDailyReportEmail(email);
    setStatus("Daily 리포트 수신을 해제했습니다.");
  };

  return (
    <main className="landing-page">
      <nav className="landing-nav">
        <a className="brand" href={ROUTES.home}>
          <span className="brand__mark" />
          <span>QuantAgent</span>
        </a>
      </nav>
      <section className="legal-page">
        <Badge variant="dark">EMAIL</Badge>
        <h1>수신 거부</h1>
        <Card className="auth-panel">
          <p>Daily 리포트 이메일 수신을 중단합니다. 마이페이지 알림 설정에서 언제든 다시 켤 수 있습니다.</p>
          <form className="form-grid" onSubmit={handleSubmit}>
            <label className="field">
              <span>이메일</span>
              <input onChange={(event) => setEmail(event.target.value)} required type="email" value={email} />
            </label>
            <div className="form-actions">
              <Button type="submit" variant="dark">수신 거부</Button>
            </div>
          </form>
          {status ? <div className="status-banner status-banner--success"><strong>{status}</strong></div> : null}
        </Card>
      </section>
      <Footer />
    </main>
  );
}
