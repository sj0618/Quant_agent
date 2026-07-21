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
  const voice = (separator >= 0 ? role.slice(separator + 1) : role) as DebateVoice;
  if (!DEBATE_VOICES.includes(voice)) {
    return null;
  }
  return { voice, phase: separator >= 0 ? role.slice(0, separator) : null };
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
    return { ...state, stage: event.stage ?? state.stage };
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

  const parsed = splitRole(event.role);
  if (!parsed) {
    // Provider calls outside the debate (screening SQL, terminology research) stream
    // too; their progress is reported as steps instead.
    return state;
  }

  const role = String(event.role);
  const { voice, phase } = parsed;
  const index = findOpenVoice(state.entries, role);

  if (event.kind === "role_started") {
    return {
      ...state,
      entries: append(state.entries, {
        id: role,
        kind: "voice",
        voice,
        phase,
        label: DEBATE_VOICE_LABELS[voice],
        detail: null,
        status: "running",
        searching: false,
        searchQueries: [],
        citations: [],
        streamingText: "",
      }),
    };
  }

  if (index < 0) {
    return state;
  }
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
