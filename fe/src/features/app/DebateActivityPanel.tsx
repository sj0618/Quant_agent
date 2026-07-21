import {
  DEBATE_VOICES,
  DEBATE_VOICE_LABELS,
  type ActivityState,
  type VoiceActivity,
} from "../../api/analysisActivity";

/** How much of the raw provider stream to keep on screen. The stream is the model's
 * JSON being written out, so it is shown as a small live trace rather than prose -
 * the readable opinion is the summary that lands when the voice finishes. */
const STREAM_TAIL_LENGTH = 220;

function VoiceRow({ activity }: { activity: VoiceActivity }) {
  const { status, phase, searching, searchQueries, citations, streamingText, summary } = activity;
  const streamTail = streamingText.slice(-STREAM_TAIL_LENGTH);
  const latestQuery = searchQueries[searchQueries.length - 1];

  return (
    <li className={`activity-log__row is-${status}`}>
      <span className="activity-log__gutter" aria-hidden="true" />
      <div className="activity-log__body">
        <p className="activity-log__head">
          <strong>{DEBATE_VOICE_LABELS[activity.voice]}</strong>
          {phase ? <span className="activity-log__phase">{phase.toLowerCase()}</span> : null}
          {status === "running" ? <span className="activity-log__status">진행 중</span> : null}
          {status === "done" ? <span className="activity-log__status is-done">완료</span> : null}
        </p>

        {searching ? <p className="activity-log__line is-search">웹 검색 중…</p> : null}
        {latestQuery ? <p className="activity-log__line is-search">🔍 {latestQuery}</p> : null}

        {summary ? (
          <p className="activity-log__line is-summary">{summary}</p>
        ) : streamTail ? (
          <p className="activity-log__line is-stream">{streamTail}</p>
        ) : status === "idle" ? (
          <p className="activity-log__line is-muted">대기 중</p>
        ) : null}

        {citations.length > 0 ? (
          <p className="activity-log__line is-citations">
            {citations.slice(-3).map((citation) => (
              <a href={citation.url} key={citation.url} rel="noreferrer noopener" target="_blank">
                {citation.title}
              </a>
            ))}
          </p>
        ) : null}
      </div>
    </li>
  );
}

export function DebateActivityPanel({ activity }: { activity: ActivityState }) {
  const hasDebate = DEBATE_VOICES.some((voice) => activity.voices[voice].status !== "idle");
  const hasSteps = activity.steps.length > 0;
  if (!hasDebate && !hasSteps) {
    return null;
  }

  return (
    <section className="activity-log">
      <ul className="activity-log__rows">
        {activity.steps.map((step, index) => (
          <li
            className={`activity-log__row is-step${
              index === activity.steps.length - 1 ? " is-latest" : ""
            }`}
            key={`${step.label}-${index}`}
          >
            <span className="activity-log__gutter" aria-hidden="true" />
            <div className="activity-log__body">
              <p className="activity-log__head">
                <strong>{step.label}</strong>
              </p>
              {step.detail ? <p className="activity-log__line is-muted">{step.detail}</p> : null}
            </div>
          </li>
        ))}

        {hasDebate
          ? DEBATE_VOICES.map((voice) => (
              <VoiceRow activity={activity.voices[voice]} key={voice} />
            ))
          : null}
      </ul>
    </section>
  );
}
