import { useEffect, useState } from "react";
import { ChevronDown, LogOut, Search, Settings, User } from "lucide-react";

import { getCurrentSession, signOut } from "@/api/authClient";
import { SearchCommand } from "@/components/layout/SearchCommand";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ROUTES, withReturnTo } from "@/config/routes";
import { cn } from "@/lib/utils";

interface TopBarProps {
  active: "workspace" | "reports" | "profile" | "search" | "landing";
}

const NAV_ITEMS = [
  { id: "workspace", label: "워크스페이스", href: ROUTES.app },
  { id: "reports", label: "리포트", href: ROUTES.reports },
] as const;

function initialsOf(name: string | undefined) {
  const trimmed = (name ?? "").trim();
  return trimmed ? trimmed.slice(0, 1).toUpperCase() : "?";
}

export function TopBar({ active }: TopBarProps) {
  const session = getCurrentSession();
  const profileHref = session ? ROUTES.me : withReturnTo(ROUTES.login, ROUTES.me);
  const [searchOpen, setSearchOpen] = useState(false);

  useEffect(() => {
    const handleKeydown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setSearchOpen((open) => !open);
      }
    };

    window.addEventListener("keydown", handleKeydown);
    return () => window.removeEventListener("keydown", handleKeydown);
  }, []);

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-line bg-surface/85 px-4 backdrop-blur-md sm:gap-6 sm:px-6">
      <a className="flex shrink-0 items-center gap-2 text-[15px] font-bold text-ink" href={ROUTES.home}>
        <span className="inline-block size-5 rounded bg-ink" />
        {/* Below sm the three groups add up to more than the viewport and the nav labels
            wrap into unreadable vertical text, so the wordmark drops to just the mark. */}
        <span className="hidden sm:inline">QuantAgent</span>
      </a>

      <nav aria-label="주요 메뉴" className="mr-auto flex items-center gap-1">
        {NAV_ITEMS.map((item) => (
          <a
            className={cn(
              "shrink-0 whitespace-nowrap rounded-lg px-2.5 py-1.5 text-[13px] font-semibold transition-colors sm:px-3",
              active === item.id ? "bg-soft text-ink" : "text-muted hover:bg-soft/70 hover:text-ink",
            )}
            href={item.href}
            key={item.id}
          >
            {item.label}
          </a>
        ))}
      </nav>

      {active !== "landing" ? (
        <div className="flex items-center gap-2">
          <button
            aria-label="검색 열기"
            className={cn(
              "group hidden h-9 w-64 items-center gap-2 rounded-full border border-line bg-soft/70 px-3.5 text-left",
              "text-[13px] text-subdued transition-colors hover:border-cornflower/50 hover:bg-surface md:flex",
            )}
            onClick={() => setSearchOpen(true)}
            type="button"
          >
            <Search aria-hidden className="size-4 shrink-0" />
            <span className="min-w-0 flex-1 truncate">전략·종목·리포트 검색</span>
            <kbd className="shrink-0 rounded border border-line bg-surface px-1.5 py-0.5 font-sans text-[10px] font-bold text-subdued">
              ⌘K
            </kbd>
          </button>
          <button
            aria-label="검색 열기"
            className="flex size-10 items-center justify-center rounded-full border border-line bg-surface text-muted md:hidden"
            onClick={() => setSearchOpen(true)}
            type="button"
          >
            <Search aria-hidden className="size-4" />
          </button>

          {session ? (
            <DropdownMenu>
              <DropdownMenuTrigger
                className={cn(
                  "flex items-center gap-2 rounded-full border border-line bg-surface py-1 pl-1 pr-2.5",
                  "text-[13px] font-semibold text-ink transition-colors hover:bg-soft outline-none",
                  "focus-visible:ring-2 focus-visible:ring-cornflower/60",
                )}
              >
                <Avatar>
                  {session.user.avatarUrl ? <AvatarImage alt="" src={session.user.avatarUrl} /> : null}
                  <AvatarFallback>{initialsOf(session.user.name)}</AvatarFallback>
                </Avatar>
                <span className="hidden max-w-28 truncate sm:inline">{session.user.name}</span>
                <ChevronDown aria-hidden className="size-3.5 text-subdued" />
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuLabel>
                  <span className="block truncate text-[13px] font-bold text-ink">{session.user.name}</span>
                  <span className="block truncate text-[11px] font-medium text-subdued">{session.user.email}</span>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem onSelect={() => window.location.assign(ROUTES.me)}>
                  <User aria-hidden className="size-4 text-subdued" />
                  마이페이지
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => window.location.assign(ROUTES.notifications)}>
                  <Settings aria-hidden className="size-4 text-subdued" />
                  알림 설정
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  className="text-drop focus:bg-drop-soft"
                  onSelect={() => {
                    void signOut().finally(() => window.location.assign(ROUTES.home));
                  }}
                >
                  <LogOut aria-hidden className="size-4" />
                  로그아웃
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          ) : (
            <a
              className="rounded-full bg-ink px-4 py-2 text-[13px] font-bold text-white transition-colors hover:bg-ink/90"
              href={profileHref}
            >
              로그인
            </a>
          )}
        </div>
      ) : null}

      <SearchCommand onOpenChange={setSearchOpen} open={searchOpen} />
    </header>
  );
}
