import { useState, type FormEvent } from "react";
import { AsyncState } from "../components/common/AsyncState";
import { Badge } from "../components/common/Badge";
import { Button } from "../components/common/Button";
import { Card } from "../components/common/Card";
import { AppLayout } from "../components/layout/AppLayout";
import { getReports } from "../api/quantAgentClient";
import { ROUTES } from "../config/routes";
import { useAsyncData } from "../hooks/useAsyncData";
import type { ReportSummary } from "../types/quantagent";

export function SearchPage() {
  const params = new URLSearchParams(window.location.search);
  const initialQuery = params.get("q") ?? "";
  const [query, setQuery] = useState(initialQuery);
  const [submittedQuery, setSubmittedQuery] = useState(initialQuery.trim());
  const normalizedQuery = submittedQuery.trim();
  const reportsState = useAsyncData(
    () => (normalizedQuery ? getReports(normalizedQuery) : Promise.resolve([] as ReportSummary[])),
    [normalizedQuery],
  );

  const reports = reportsState.data ?? [];

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextQuery = query.trim();
    setSubmittedQuery(nextQuery);
    const url = new URL(window.location.href);
    if (nextQuery) {
      url.searchParams.set("q", nextQuery);
    } else {
      url.searchParams.delete("q");
    }
    window.history.replaceState({}, "", url);
  };

  if (reportsState.loading && !reportsState.data) {
    return <AsyncState title="검색 데이터를 불러오는 중입니다" tone="loading" />;
  }

  if (reportsState.error || !reportsState.data) {
    return <AsyncState title="검색 데이터를 불러오지 못했습니다" description={reportsState.error?.message} tone="error" />;
  }

  return (
    <AppLayout active="search">
      <main className="search-page">
        <form className="search-form" onSubmit={handleSubmit}>
          <label>
            <span>검색어</span>
            <input
              autoFocus
              onChange={(event) => setQuery(event.target.value)}
              placeholder="리포트 제목, 전략명, 후보명, 티커"
              value={query}
            />
          </label>
          <Button type="submit" variant="dark">
            검색
          </Button>
        </form>

        <div className="search-results-head">
          <strong>{normalizedQuery ? `"${normalizedQuery}" 검색 결과` : "검색어를 입력하세요"}</strong>
          <span>{reports.length}건</span>
        </div>

        <section className="search-results">
          {normalizedQuery && reports.length === 0 ? (
            <Card>
              <strong>검색 결과가 없습니다</strong>
              <p>리포트 제목, 요약, 전략명, 후보명, 티커를 다시 확인해보세요.</p>
            </Card>
          ) : null}

          {reports.map((report) => (
            <a className="search-result-row" href={ROUTES.reportDetail(report.id)} key={report.id}>
              <Badge variant="info">report</Badge>
              <span>
                <strong>{report.title}</strong>
                <small>{report.summary}</small>
              </span>
              <em>{`${report.date} · ${report.recommendationScore}`}</em>
            </a>
          ))}
        </section>
      </main>
    </AppLayout>
  );
}
