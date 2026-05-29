import { useEffect } from "react";
import { getCurrentSession } from "../../api/authClient";
import { ROUTES, withReturnTo } from "../../config/routes";

interface TopBarProps {
  active: "workspace" | "reports" | "profile" | "search" | "landing";
}

export function TopBar({ active }: TopBarProps) {
  const session = getCurrentSession();
  const profileHref = session ? ROUTES.me : withReturnTo(ROUTES.login, ROUTES.me);

  useEffect(() => {
    const handleKeydown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        window.location.assign(ROUTES.search);
      }
    };

    window.addEventListener("keydown", handleKeydown);
    return () => window.removeEventListener("keydown", handleKeydown);
  }, []);

  return (
    <header className="topbar">
      <a className="brand" href={ROUTES.home}>
        <span className="brand__mark" />
        <span>QuantAgent</span>
      </a>
      <nav className="topbar__nav" aria-label="주요 메뉴">
        <a className={active === "workspace" ? "is-active" : ""} href={ROUTES.app}>
          워크스페이스
        </a>
        <a className={active === "reports" ? "is-active" : ""} href={ROUTES.reports}>
          리포트
        </a>
        <a className={active === "profile" ? "is-active" : ""} href={profileHref}>
          마이페이지
        </a>
      </nav>
      {active !== "landing" ? (
        <div className="topbar__right">
          <a className={["search-pill", active === "search" ? "is-active" : ""].filter(Boolean).join(" ")} href={ROUTES.search}>
            <span>🔍</span>
            <span>전략·종목·리포트 검색</span>
            <kbd>⌘ K</kbd>
          </a>
          <a className="user-pill" href={profileHref}>
            <span>{session?.user.name ?? "로그인"}</span>
            <span className="avatar" />
          </a>
        </div>
      ) : null}
    </header>
  );
}
