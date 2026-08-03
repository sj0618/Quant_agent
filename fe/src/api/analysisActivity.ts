import { useEffect, useReducer } from "react";

import { appConfig, AI_ENDPOINTS } from "../config/appConfig";

/** 정/반/합. Roles arrive phase-qualified (RESEARCH_BULL, SIGNAL_BEAR, ...). */
export type DebateVoice = "BULL" | "BEAR" | "JUDGE";

const DEBATE_VOICES: DebateVoice[] = ["BULL", "BEAR", "JUDGE"];

export const DEBATE_VOICE_LABELS: Record<DebateVoice, string> = {
  BULL: "정 · 지지",
  BEAR: "반 · 반론",
  JUDGE: "합 · 판단",
};

/** Single-lane provider calls that aren't a 정/반/합 debate but still stream live
 * activity (search, text deltas, citations) worth showing while they run. */
const SOLO_ROLE_LABELS: Record<string, string> = {
  BACKTEST_CODE: "코드 생성",
  STRATEGY_CONDITIONS: "매수/매도 조건 생성",
  REPORT_WRITER: "리포트 작성",
};

/** Where provider calls that carry no role are shown.
 *
 * Screening and terminology research stream search queries, citations and text deltas
 * without a debate role. Those events used to be dropped outright, so the whole 전략 해석
 * stage looked idle even while the model was visibly working. */
const UNLABELLED_ROLE_ID = "PROVIDER";
const UNLABELLED_ROLE_LABEL = "리서치";

/** The log is a tail, not an audit trail - old entries scroll out of view. */
const MAX_ENTRIES = 14;

export interface Citation {
  title: string;
  url: string;
}

/** One line of the run, in the order it happened.
 *
 * Debate voices used to live in three fixed slots updated in place while computation
 * steps appended to a list, so the two never shared an ordering: the screen showed a
 * backtest step above a debate that had finished before it. Everything is one sequence
 * now, and a voice's own entry is updated in place as its text streams in.
 */
export interface ActivityEntry {
  id: string;
  kind: "step" | "voice";
  label: string;
  detail: string | null;
  status: "running" | "done";
  /** Voice entries only. */
  voice?: DebateVoice;
  phase?: string | null;
  searching?: boolean;
  searchQueries?: string[];
  citations?: Citation[];
  streamingText?: string;
}

export interface ActivityState {
  stage: string | null;
  entries: ActivityEntry[];
}

interface ActivityEvent {
  kind: string;
  role?: string | null;
  stage?: string;
  label?: string;
  detail?: string;
  text?: string;
  queries?: string[];
  title?: string;
  url?: string;
  summary?: string;
  evidence?: string[];
  concerns?: string[];
}

export function emptyActivityState(): ActivityState {
  return { stage: null, entries: [] };
}

function splitRole(role: string | null | undefined) {
  if (!role) {
    return null;
  }
  const separator = role.lastIndexOf("_");
  const suffix = (separator >= 0 ? role.slice(separator + 1) : role) as DebateVoice;
  if (DEBATE_VOICES.includes(suffix)) {
    return {
      voice: suffix as DebateVoice | null,
      phase: separator >= 0 ? role.slice(0, separator) : null,
      label: DEBATE_VOICE_LABELS[suffix],
    };
  }
  const soloLabel = SOLO_ROLE_LABELS[role];
  if (!soloLabel) {
    return null;
  }
  return { voice: null, phase: null, label: soloLabel };
}

/** Events with no role still belong somewhere; they share one "리서치" lane. */
function resolveRole(role: string | null | undefined) {
  const parsed = splitRole(role);
  if (parsed) {
    return { id: String(role), ...parsed };
  }
  return { id: UNLABELLED_ROLE_ID, voice: null, phase: null, label: UNLABELLED_ROLE_LABEL };
}

/** The open entry for a role, so streamed text lands on the line it belongs to. */
function findOpenVoice(entries: ActivityEntry[], role: string): number {
  for (let index = entries.length - 1; index >= 0; index -= 1) {
    const entry = entries[index];
    if (entry.kind === "voice" && entry.id === role && entry.status === "running") {
      return index;
    }
  }
  return -1;
}

function replaceAt(
  entries: ActivityEntry[],
  index: number,
  update: Partial<ActivityEntry>,
): ActivityEntry[] {
  const next = [...entries];
  next[index] = { ...next[index], ...update };
  return next;
}

function append(entries: ActivityEntry[], entry: ActivityEntry): ActivityEntry[] {
  return [...entries, entry].slice(-MAX_ENTRIES);
}

function reduce(state: ActivityState, event: ActivityEvent): ActivityState {
  if (event.kind === "stage") {
    // Roleless provider calls have no completion event of their own, so their lane is
    // closed when the run moves to the next stage - otherwise it spins forever.
    return {
      ...state,
      stage: event.stage ?? state.stage,
      entries: state.entries.map((entry) =>
        entry.id === UNLABELLED_ROLE_ID && entry.status === "running"
          ? { ...entry, status: "done", searching: false }
          : entry,
      ),
    };
  }

  if (event.kind === "step") {
    if (!event.label) {
      return state;
    }
    return {
      ...state,
      entries: append(state.entries, {
        id: `step-${state.entries.length}-${event.label}`,
        kind: "step",
        label: event.label,
        detail: event.detail ?? null,
        status: "done",
      }),
    };
  }

  const { id: role, voice, phase, label } = resolveRole(event.role);
  const openEntry = (entries: ActivityEntry[]) =>
    append(entries, {
      id: role,
      kind: "voice",
      voice: voice ?? undefined,
      phase,
      label,
      detail: null,
      status: "running",
      searching: false,
      searchQueries: [],
      citations: [],
      streamingText: "",
    });

  if (event.kind === "role_started") {
    return { ...state, entries: openEntry(state.entries) };
  }

  // Roleless provider calls never send role_started, so their lane is opened on the first
  // event that arrives instead of dropping everything until one that never comes.
  let entries = state.entries;
  let index = findOpenVoice(entries, role);
  if (index < 0) {
    if (role !== UNLABELLED_ROLE_ID) {
      return state;
    }
    entries = openEntry(entries);
    index = findOpenVoice(entries, role);
    if (index < 0) {
      return state;
    }
  }
  state = { ...state, entries };
  const current = state.entries[index];

  switch (event.kind) {
    case "search_started":
      return { ...state, entries: replaceAt(state.entries, index, { searching: true }) };
    case "search_queries":
      return {
        ...state,
        entries: replaceAt(state.entries, index, {
          searching: false,
          searchQueries: [...(current.searchQueries ?? []), ...(event.queries ?? [])],
        }),
      };
    case "citation": {
      if (!event.url || (current.citations ?? []).some((item) => item.url === event.url)) {
        return state;
      }
      return {
        ...state,
        entries: replaceAt(state.entries, index, {
          citations: [
            ...(current.citations ?? []),
            { title: event.title || event.url, url: event.url },
          ],
        }),
      };
    }
    case "text_delta":
      return {
        ...state,
        entries: replaceAt(state.entries, index, {
          streamingText: (current.streamingText ?? "") + (event.text ?? ""),
        }),
      };
    case "role_completed":
      return {
        ...state,
        entries: replaceAt(state.entries, index, {
          status: "done",
          searching: false,
          detail: event.summary ?? current.detail,
        }),
      };
    default:
      return state;
  }
}

type Action = { type: "event"; event: ActivityEvent } | { type: "reset" };

function activityReducer(state: ActivityState, action: Action): ActivityState {
  if (action.type === "reset") {
    return emptyActivityState();
  }
  return reduce(state, action.event);
}

/** Subscribe to a running job's provider activity. */
export function useAnalysisActivity(jobId: string | null | undefined): ActivityState {
  const [state, dispatch] = useReducer(activityReducer, undefined, emptyActivityState);

  useEffect(() => {
    dispatch({ type: "reset" });
    if (!jobId || !appConfig.aiApiBaseUrl) {
      return undefined;
    }

    const source = new EventSource(
      `${appConfig.aiApiBaseUrl}${AI_ENDPOINTS.analysisJobEvents(jobId)}`,
      { withCredentials: true },
    );

    source.onmessage = (message) => {
      try {
        dispatch({ type: "event", event: JSON.parse(message.data) as ActivityEvent });
      } catch (error) {
        console.warn("분석 활동 이벤트를 해석하지 못했습니다.", error);
      }
    };
    source.addEventListener("done", () => source.close());
    // Deliberately no close on error: EventSource reconnects on its own and the server
    // replays from Last-Event-ID, so a dropped connection resumes instead of leaving
    // the panel blank for the rest of the run.
    source.onerror = () => {
      console.warn("분석 활동 스트림이 끊겨 재연결을 시도합니다.");
    };

    return () => source.close();
  }, [jobId]);

  return state;
}
