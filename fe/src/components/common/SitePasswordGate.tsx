// TEMP(dev-auth-gate): whole file. Delete this file and its one usage in App.tsx once
// the product is ready for public access / BE session integration ships.
import { useState, type FormEvent, type ReactNode } from "react";
import { appConfig } from "../../config/appConfig";

const UNLOCK_STORAGE_KEY = "quantagent.site-gate.v1";

async function sha256Hex(text: string): Promise<string> {
  const bytes = new TextEncoder().encode(text);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

function isUnlocked(): boolean {
  return window.localStorage.getItem(UNLOCK_STORAGE_KEY) === "1";
}

export function SitePasswordGate({ children }: { children: ReactNode }) {
  const [unlocked, setUnlocked] = useState(isUnlocked);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);

  if (!appConfig.sitePasswordGateEnabled || unlocked) {
    return <>{children}</>;
  }

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setChecking(true);
    setError(null);

    const nowSeconds = Math.floor(Date.now() / 1000);
    const activeEntries = appConfig.sitePasswordEntries.filter((entry) => entry.expiresAt > nowSeconds);
    if (activeEntries.length === 0) {
      setError("접근 기간이 만료되었습니다. 담당자에게 새 비밀번호를 요청하세요.");
      setChecking(false);
      return;
    }

    let matched = false;
    for (const entry of activeEntries) {
      const candidate = await sha256Hex(`${entry.salt}:${password}`);
      if (candidate === entry.hash) {
        matched = true;
        break;
      }
    }

    if (matched) {
      window.localStorage.setItem(UNLOCK_STORAGE_KEY, "1");
      setUnlocked(true);
    } else {
      setError("비밀번호가 올바르지 않습니다.");
    }
    setChecking(false);
  };

  return (
    <div className="site-gate-overlay">
      <form className="site-gate-modal" onSubmit={handleSubmit}>
        <h1>비공개 베타</h1>
        <p>접근 비밀번호를 입력하세요.</p>
        <input
          autoFocus
          onChange={(event) => setPassword(event.target.value)}
          placeholder="비밀번호"
          type="password"
          value={password}
        />
        {error ? <p className="site-gate-modal__error">{error}</p> : null}
        <button disabled={checking || !password} type="submit">
          {checking ? "확인 중" : "입장하기"}
        </button>
      </form>
    </div>
  );
}
