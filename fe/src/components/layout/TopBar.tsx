interface TopBarProps {
  active: "workspace" | "reports" | "landing";
}

export function TopBar({ active }: TopBarProps) {
  return (
    <header className="topbar">
      <a className="brand" href="/">
        <span className="brand__mark" />
        <span>QuantAgent</span>
      </a>
      <nav className="topbar__nav" aria-label="주요 메뉴">
        <a className={active === "workspace" ? "is-active" : ""} href="/app">
          워크스페이스
        </a>
        <a className={active === "reports" ? "is-active" : ""} href="/reports">
          리포트
        </a>
        <span className="topbar__disabled">마이페이지</span>
      </nav>
      {active !== "landing" ? (
        <div className="topbar__right">
          <div className="search-pill">
            <span>🔍</span>
            <span>전략·종목·리포트 검색</span>
            <kbd>⌘ K</kbd>
          </div>
          <div className="user-pill">
            <span>홍길동</span>
            <span className="avatar" />
          </div>
        </div>
      ) : null}
    </header>
  );
}
