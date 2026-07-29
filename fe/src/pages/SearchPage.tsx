import { useMemo, useState, type FormEvent } from "react";
import { AsyncState } from "../components/common/AsyncState";
import { Badge } from "../components/common/Badge";
import { Button } from "../components/common/Button";
import { Card } from "../components/common/Card";
import { AppLayout } from "../components/layout/AppLayout";
import {
  getReports,
  getWorkspaceTemplate,
  mergeAnalysisJobIntoOverview,
  refreshLatestAnalysisJob,
} from "../api/quantAgentClient";
import { ROUTES } from "../config/routes";
import { useAsyncData } from "../hooks/useAsyncData";
import type { AppOverview, ReportSummary, TradingCandidate } from "../types/quantagent";

type SearchResultKind = "strategy" | "candidate" | "report";

type SearchResult = {
  key: string;
  kind: SearchResultKind;
  title: string;
  description: string;
  href: string;
  meta: string;
};

function includesQuery(value: string | null | undefined, query: string) {
  return Boolean(value && value.toLowerCase().includes(query.toLowerCase()));
}

function buildStrategyResults(overview: AppOverview | null, query: string): SearchResult[] {
  const normalized = query.trim();
  if (!overview || !normalized) {
    return [];
  }

  const strategy = overview.strategy;
  const searchableValues = [
    strategy.name,
    strategy.natural_language_strategy,
    strategy.sector,
    strategy.buy_condition,
    strategy.hold_condition,
    strategy.drop_condition,
    strategy.rebalance,
    strategy.constraints.join(" "),
  ];
  if (!searchableValues.some((value) => includesQuery(value, normalized))) {
    return [];
  }

  const title = strategy.name?.trim() || "현재 전략";
  const description =
    strategy.natural_language_strategy?.trim() ||
    strategy.buy_condition?.trim() ||
    strategy.sector?.trim() ||
    "현재 작업공간의 전략";

  return [
    {
      key: "workspace:strategy",
      kind: "strategy",
      title,
      description,
      href: ROUTES.app,
      meta: overview.latestRunLabel,
    },
  ];
}

function buildCandidateResults(candidates: TradingCandidate[], query: string): SearchResult[] {
  const normalized = query.trim();
  if (!normalized) {
    return [];
  }

  return candidates
    .filter((candidate) =>
      [
        candidate.name,
        candidate.ticker,
        candidate.sector,
        candidate.signal,
        candidate.rationale,
        candidate.price,
        candidate.changePercent,
        candidate.riskReasons.join(" "),
      ].some((value) => includesQuery(value, normalized)),
    )
    .map<SearchResult>((candidate) => ({
      key: `candidate:${candidate.id}`,
      kind: "candidate",
      title: `${candidate.name} ${candidate.ticker}`.trim(),
      description: candidate.rationale || candidate.sector || "현재 작업공간의 매매종목",
      href: `${ROUTES.app}?tab=trading`,
      meta: `${candidate.signal} · ${candidate.confidence.toFixed(1)} · ${candidate.price}`,
    }));
}

function buildReportResults(reports: ReportSummary[], query: string): SearchResult[] {
  const normalized = query.trim();
  if (!normalized) {
    return [];
  }

  return reports
    .filter((report) => [report.title, report.summary, report.strategyName, report.date, report.weekday].some((value) => includesQuery(value, normalized)))
    .map<SearchResult>((report) => ({
      key: `report:${report.id}`,
      kind: "report",
      title: report.title,
      description: report.summary,
      href: ROUTES.reportDetail(report.id),
      meta: `${report.date} · ${report.recommendationScore}`,
    }));
}

async function loadWorkspaceSearchOverview() {
  const template = await getWorkspaceTemplate();
  try {
    const latestJob = await refreshLatestAnalysisJob();
    return latestJob ? mergeAnalysisJobIntoOverview(template, latestJob) : template;
  } catch {
    return template;
  }
}

export function SearchPage() {
  const params = new URLSearchParams(window.location.search);
  const initialQuery = params.get("q") ?? "";
  const [query, setQuery] = useState(initialQuery);
  const reportsState = useAsyncData(getReports, []);
  const workspaceState = useAsyncData(loadWorkspaceSearchOverview, []);

  const reports = reportsState.data ?? [];
  const workspace = workspaceState.data;
  const results = useMemo(
    () => [...buildStrategyResults(workspace, query), ...buildCandidateResults(workspace?.candidates ?? [], query), ...buildReportResults(reports, query)],
    [reports, query, workspace],
  );

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
              placeholder="전략, 종목, 리포트"
              value={query}
            />
          </label>
          <Button type="submit" variant="dark">
            검색
          </Button>
        </form>

        <div className="search-results-head">
          <strong>{query.trim() ? `"${query.trim()}" 검색 결과` : "검색어를 입력하세요"}</strong>
          <span>{results.length}건</span>
        </div>

        <section className="search-results">
          {query.trim() && results.length === 0 ? (
            <Card>
              <strong>검색 결과가 없습니다</strong>
              <p>현재 작업공간 전략, 매매종목, 생성 리포트 중에서 다시 검색해보세요.</p>
            </Card>
          ) : null}

          {results.map((result) => (
            <a className="search-result-row" href={result.href} key={result.key}>
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
