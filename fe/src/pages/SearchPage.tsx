import { useMemo, useState, type FormEvent } from "react";
import { AsyncState } from "../components/common/AsyncState";
import { Badge } from "../components/common/Badge";
import { Button } from "../components/common/Button";
import { Card } from "../components/common/Card";
import { AppLayout } from "../components/layout/AppLayout";
import { getReports } from "../api/quantAgentClient";
import { ROUTES } from "../config/routes";
import { useAsyncData } from "../hooks/useAsyncData";

type SearchResult = {
  id: string;
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
  const { data, loading, error } = useAsyncData(getReports, []);

  const results = useMemo<SearchResult[]>(() => {
    if (!data || !query.trim()) {
      return [];
    }

    const normalized = query.trim();
    return data
      .filter((report) => [report.title, report.summary, report.date].some((value) => includesQuery(value, normalized)))
      .map<SearchResult>((report) => ({
        id: report.id,
        title: report.title,
        description: report.summary,
        href: ROUTES.reportDetail(report.id),
        meta: `${report.date} · 권장도 ${report.recommendationScore}`,
      }));
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
    return <AsyncState title="리포트 검색 데이터를 불러오는 중입니다" tone="loading" />;
  }

  if (error || !data) {
    return <AsyncState title="리포트 검색 데이터를 불러오지 못했습니다" description={error?.message} tone="error" />;
  }

  return (
    <AppLayout active="search">
      <main className="search-page">
        <form className="search-form" onSubmit={handleSubmit}>
          <label>
            <span>리포트 검색</span>
            <input
              autoFocus
              onChange={(event) => setQuery(event.target.value)}
              placeholder="내 리포트 제목 또는 요약 검색"
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
              <p>내가 만든 리포트 제목 또는 요약을 다시 확인해 주세요.</p>
            </Card>
          ) : null}

          {results.map((result) => (
            <a className="search-result-row" href={result.href} key={result.id}>
              <Badge variant="info">리포트</Badge>
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
