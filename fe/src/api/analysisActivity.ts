import { useEffect, useReducer } from "react";

import { appConfig, AI_ENDPOINTS } from "../config/appConfig";

/** 정/반/합. Roles arrive phase-qualified (RESEARCH_BULL, SIGNAL_BEAR, ...), and every
 * phase debates the same three ways, so activity is grouped by the voice and the panel
 * shows whichever phase is currently speaking. */
export type DebateVoice = "BULL" | "BEAR" | "JUDGE";

export const DEBATE_VOICES: DebateVoice[] = ["BULL", "BEAR", "JUDGE"];

export const DEBATE_VOICE_LABELS: Record<DebateVoice, string> = {
  BULL: "정 · 지지 근거",
  BEAR: "반 · 반론과 위험",
  JUDGE: "합 · 종합 판단",
};

export interface Citation {
  title: string;
  url: string;
}

export interface VoiceActivity {
  voice: DebateVoice;
  phase: string | null;
  status: "idle" | "running" | "done";
  searchQueries: string[];
  citations: Citation[];
  streamingText: string;
  summary: string | null;
  evidence: string[];
  concerns: string[];
  searching: boolean;
}

export interface ActivityState {
  stage: string | null;
  voices: Record<DebateVoice, VoiceActivity>;
}

interface ActivityEvent {
  kind: string;
  role?: string | null;
  stage?: string;
  text?: string;
  queries?: string[];
  title?: string;
  url?: string;
  summary?: string;
  evidence?: string[];
  concerns?: string[];
}

function emptyVoice(voice: DebateVoice): VoiceActivity {
  return {
    voice,
    phase: null,
    status: "idle",
    searchQueries: [],
    citations: [],
    streamingText: "",
    summary: null,
    evidence: [],
    concerns: [],
    searching: false,
  };
}

export function emptyActivityState(): ActivityState {
  return {
    stage: null,
    voices: {
      BULL: emptyVoice("BULL"),
      BEAR: emptyVoice("BEAR"),
      JUDGE: emptyVoice("JUDGE"),
    },
  };
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

function reduce(state: ActivityState, event: ActivityEvent): ActivityState {
  if (event.kind === "stage") {
    return { ...state, stage: event.stage ?? state.stage };
  }

  const parsed = splitRole(event.role);
  if (!parsed) {
    // Provider calls outside the debate (strategy conditions, market brief) still
    // stream; they have no section to belong to, so they are not shown.
    return state;
  }

  const { voice, phase } = parsed;
  const current = state.voices[voice];
  let next: VoiceActivity;

  switch (event.kind) {
    case "role_started":
      // A new phase reuses the section, so its prior content is cleared rather than
      // appended to - otherwise research and report opinions would run together.
      next = { ...emptyVoice(voice), phase, status: "running" };
      break;
    case "search_started":
      next = { ...current, searching: true };
      break;
    case "search_queries":
      next = {
        ...current,
        searching: false,
        searchQueries: [...current.searchQueries, ...(event.queries ?? [])],
      };
      break;
    case "citation": {
      if (!event.url) {
        return state;
      }
      const known = current.citations.some((item) => item.url === event.url);
      next = known
        ? current
        : {
            ...current,
            citations: [...current.citations, { title: event.title || event.url, url: event.url }],
          };
      break;
    }
    case "text_delta":
      next = { ...current, streamingText: current.streamingText + (event.text ?? "") };
      break;
    case "role_completed":
      next = {
        ...current,
        status: "done",
        searching: false,
        summary: event.summary ?? null,
        evidence: event.evidence ?? [],
        concerns: event.concerns ?? [],
      };
      break;
    default:
      return state;
  }

  return { ...state, voices: { ...state.voices, [voice]: next } };
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
    // The stream also ends when the job finishes; an error here just means no more
    // live updates, and the polled job still carries the final result.
    source.onerror = () => source.close();

    return () => source.close();
  }, [jobId]);

  return state;
}
