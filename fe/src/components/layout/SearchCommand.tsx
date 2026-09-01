import { useEffect, useRef, useState } from "react";
import { ArrowRight, FileText, LayoutDashboard, Settings } from "lucide-react";

import { getReports } from "@/api/quantAgentClient";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { ROUTES } from "@/config/routes";
import type { ReportSummary } from "@/types/quantagent";

const SEARCH_DEBOUNCE_MS = 220;
const RESULT_LIMIT = 6;

interface SearchCommandProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** ⌘K palette.
 *
 * The top bar used to show a search-shaped link that navigated to `/search` - a full page
 * load before you could type the first character. This searches in place; `/search` is
 * still there for the full result list and for anyone who lands on it directly.
 */
export function SearchCommand({ open, onOpenChange }: SearchCommandProps) {
  const [query, setQuery] = useState("");
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const requestIdRef = useRef(0);

  useEffect(() => {
    if (!open) {
      setQuery("");
      setReports([]);
      return;
    }
    const trimmed = query.trim();
    if (!trimmed) {
      setReports([]);
      setLoading(false);
      return;
    }

    setLoading(true);
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    const timeoutId = window.setTimeout(() => {
      getReports(trimmed)
        .then((results) => {
          // Ignore anything that came back after a newer keystroke.
          if (requestIdRef.current === requestId) {
            setReports(results.slice(0, RESULT_LIMIT));
          }
        })
        .catch(() => {
          if (requestIdRef.current === requestId) {
            setReports([]);
          }
        })
        .finally(() => {
          if (requestIdRef.current === requestId) {
            setLoading(false);
          }
        });
    }, SEARCH_DEBOUNCE_MS);

    return () => window.clearTimeout(timeoutId);
  }, [open, query]);

  const go = (href: string) => {
    onOpenChange(false);
    window.location.assign(href);
  };

  const trimmedQuery = query.trim();

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      {/* cmdk filters client-side by default; results here already come filtered from the server. */}
      <CommandInput
        onValueChange={setQuery}
        placeholder="전략·종목·리포트 검색"
        value={query}
      />
      <CommandList>
        {trimmedQuery ? (
          <>
            {loading ? <div className="px-4 py-6 text-center text-[13px] text-subdued">검색 중입니다…</div> : null}
            {!loading && reports.length === 0 ? <CommandEmpty>검색 결과가 없습니다.</CommandEmpty> : null}
            {reports.length ? (
              <CommandGroup heading="리포트">
                {reports.map((report) => (
                  <CommandItem key={report.id} value={report.id} onSelect={() => go(ROUTES.reportDetail(report.id))}>
                    <FileText aria-hidden className="size-4 text-subdued" />
                    <span className="min-w-0 flex-1 truncate">{report.title}</span>
                    <span className="shrink-0 text-[11px] font-bold text-subdued">{report.date}</span>
                  </CommandItem>
                ))}
              </CommandGroup>
            ) : null}
            <CommandGroup heading="더 보기">
              <CommandItem
                value="all-results"
                onSelect={() => go(`${ROUTES.search}?q=${encodeURIComponent(trimmedQuery)}`)}
              >
                <ArrowRight aria-hidden className="size-4 text-subdued" />
                <span>{`"${trimmedQuery}" 전체 결과 보기`}</span>
              </CommandItem>
            </CommandGroup>
          </>
        ) : (
          <CommandGroup heading="바로 가기">
            <CommandItem value="workspace" onSelect={() => go(ROUTES.app)}>
              <LayoutDashboard aria-hidden className="size-4 text-subdued" />
              <span>워크스페이스</span>
            </CommandItem>
            <CommandItem value="reports" onSelect={() => go(ROUTES.reports)}>
              <FileText aria-hidden className="size-4 text-subdued" />
              <span>리포트</span>
            </CommandItem>
            <CommandItem value="notifications" onSelect={() => go(ROUTES.notifications)}>
              <Settings aria-hidden className="size-4 text-subdued" />
              <span>알림 설정</span>
            </CommandItem>
          </CommandGroup>
        )}
      </CommandList>
    </CommandDialog>
  );
}
