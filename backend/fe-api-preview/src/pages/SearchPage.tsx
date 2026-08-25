import { useMemo, useState, type FormEvent } from "react";
import { AsyncState } from "../components/common/AsyncState";
import { Badge } from "../components/common/Badge";
import { Button } from "../components/common/Button";
import { Card } from "../components/common/Card";
import { AppLayout } from "../components/layout/AppLayout";
import { getAppOverview, getReports } from "../api/quantAgentClient";
import { ROUTES } from "../config/routes";
import { useAsyncData } from "../hooks/useAsyncData";

type SearchResult = {
  kind: "strategy" | "candidate" | "report";
  title: string;
  description: string;
  href: string;
  meta: string;
};

function includesQuery(value: string, query: string) {
  return value.toLowerCase().includes(query.toLowerCase());
}

export function SearchPage() {
  const params = new URLSearchParams(window.location.search);
  const initialQuery = params.get("q") ?? "";
  const [query, setQuery] = useState(initialQuery);
  const { data, loading, error } = useAsyncData(async () => {
    const [overview, reports] = await Promise.all([getAppOverview(), getReports()]);
    return { overview, reports };
  }, []);

  const results = useMemo<SearchResult[]>(() => {
    if (!data || !query.trim()) {
      return [];
    }

    const normalized = query.trim();
    const strategyResults: SearchResult[] = includesQuery(data.overview.strategy.natural_language_strategy, normalized)
      ? [
          {
            kind: "strategy",
            title: "활성 전략",
            description: data.overview.strategy.natural_language_strategy,
            href: ROUTES.app,
            meta: data.overview.strategy.sector,
          },
        ]
      : [];

    const candidateResults = data.overview.candidates
      .filter((candidate) =>
        [candidate.name, candidate.ticker, candidate.sector, candidate.rationale].some((value) => includesQuery(value, normalized)),
      )
      .map<SearchResult>((candidate) => ({
        kind: "candidate",
        title: `${candidate.name} ${candidate.ticker}`,
        description: candidate.rationale,
        href: `${ROUTES.app}?tab=trading`,
        meta: `${candidate.signal} · ${candidate.score.toFixed(2)}`,
      }));

    const reportResults = data.reports
      .filter((report) => [report.title, report.summary, report.strategyName, report.date].some((value) => includesQuery(value, normalized)))
      .map<SearchResult>((report) => ({
        kind: "report",
        title: report.title,
        description: report.summary,
        href: ROUTES.reportDetail(report.id),
        meta: `${report.date} · 권장도 ${report.recommendationScore}`,
      }));

    return [...strategyResults, ...candidateResults, ...reportResults];
  }, [data, query]);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const url = new URL(window.location.href);
    if (query.trim()) {
      url.searchParams.set("q", query.trim());
    } else {
      url.searchParams.delete("q");
    }
    window.history.replaceState({}, "", url);
  };

  if (loading) {
    return <AsyncState title="검색 데이터를 불러오는 중입니다" tone="loading" />;
  }

  if (error || !data) {
    return <AsyncState title="검색 데이터를 불러오지 못했습니다" description={error?.message} tone="error" />;
  }

  return (
    <AppLayout active="search">
      <main className="search-page">
        <form className="search-form" onSubmit={handleSubmit}>
          <label>
            <span>통합 검색</span>
            <input
              autoFocus
              onChange={(event) => setQuery(event.target.value)}
              placeholder="전략, 종목, 리포트 검색"
              value={query}
            />
          </label>
          <Button type="submit" variant="dark">검색</Button>
        </form>

        <div className="search-results-head">
          <strong>{query.trim() ? `"${query.trim()}" 검색 결과` : "검색어를 입력하세요"}</strong>
          <span>{results.length}건</span>
        </div>

        <section className="search-results">
          {query.trim() && results.length === 0 ? (
            <Card>
              <strong>검색 결과가 없습니다</strong>
              <p>전략명, 종목명, 티커, 리포트 제목을 다시 확인하세요.</p>
            </Card>
          ) : null}

          {results.map((result) => (
            <a className="search-result-row" href={result.href} key={`${result.kind}-${result.title}`}>
              <Badge variant={result.kind === "report" ? "info" : result.kind === "candidate" ? "dark" : "soft"}>
                {result.kind}
              </Badge>
              <span>
                <strong>{result.title}</strong>
                <small>{result.description}</small>
              </span>
              <em>{result.meta}</em>
            </a>
          ))}
        </section>
      </main>
    </AppLayout>
  );
}
