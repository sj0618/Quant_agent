import {
  DEBATE_VOICES,
  DEBATE_VOICE_LABELS,
  type ActivityState,
  type VoiceActivity,
} from "../../api/analysisActivity";

/** How much of the raw provider stream to keep on screen. The stream is the model's
 * JSON being written out, so it is shown as a small live trace rather than prose -
 * the readable opinion is the summary that lands when the voice finishes. */
const STREAM_TAIL_LENGTH = 180;

function VoiceSection({ activity }: { activity: VoiceActivity }) {
  const { status, phase, searching, searchQueries, citations, streamingText, summary } = activity;
  const streamTail = streamingText.slice(-STREAM_TAIL_LENGTH);

  return (
    <li className={`debate-activity__voice is-${status}`}>
      <div className="debate-activity__voice-head">
        <strong>{DEBATE_VOICE_LABELS[activity.voice]}</strong>
        {phase ? <span className="debate-activity__phase">{phase.toLowerCase()}</span> : null}
      </div>

      {status === "idle" ? <p className="debate-activity__idle">대기 중</p> : null}

      {searching ? <p className="debate-activity__searching">웹 검색 중…</p> : null}

      {searchQueries.length > 0 ? (
        <ul className="debate-activity__queries">
          {searchQueries.slice(-3).map((query) => (
            <li key={query}>{query}</li>
          ))}
        </ul>
      ) : null}

      {summary ? (
        <p className="debate-activity__summary">{summary}</p>
      ) : streamTail ? (
        <p className="debate-activity__stream">{streamTail}</p>
      ) : null}

      {citations.length > 0 ? (
        <ul className="debate-activity__citations">
          {citations.slice(-3).map((citation) => (
            <li key={citation.url}>
              <a href={citation.url} rel="noreferrer noopener" target="_blank">
                {citation.title}
              </a>
            </li>
          ))}
        </ul>
      ) : null}
    </li>
  );
}

export function DebateActivityPanel({ activity }: { activity: ActivityState }) {
  const hasActivity = DEBATE_VOICES.some(
    (voice) => activity.voices[voice].status !== "idle",
  );
  if (!hasActivity) {
    return null;
  }

  return (
    <section className="debate-activity">
      <p className="debate-activity__caption">정·반·합 토론 진행 상황</p>
      <ul className="debate-activity__voices">
        {DEBATE_VOICES.map((voice) => (
          <VoiceSection activity={activity.voices[voice]} key={voice} />
        ))}
      </ul>
    </section>
  );
}
