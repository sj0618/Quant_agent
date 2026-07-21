import type { ActivityEntry, ActivityState } from "../../api/analysisActivity";

/** How much of the raw provider stream to keep on screen. It is the model's JSON being
 * written out, so it reads as a live trace until the finished summary replaces it. */
const STREAM_TAIL_LENGTH = 200;

function EntryRow({ entry, isLatest }: { entry: ActivityEntry; isLatest: boolean }) {
  const streamTail = (entry.streamingText ?? "").slice(-STREAM_TAIL_LENGTH);
  const latestQuery = entry.searchQueries?.[entry.searchQueries.length - 1];
  const citations = entry.citations ?? [];

  return (
    <li
      className={`activity-log__row is-${entry.status}${entry.kind === "voice" ? " is-voice" : ""}${
        isLatest ? " is-latest" : ""
      }`}
    >
      <span className="activity-log__gutter" aria-hidden="true" />
      <div className="activity-log__body">
        <p className="activity-log__head">
          <strong>{entry.label}</strong>
          {entry.phase ? <span className="activity-log__phase">{entry.phase.toLowerCase()}</span> : null}
          {entry.status === "running" ? <span className="activity-log__status">진행 중</span> : null}
        </p>

        {entry.searching ? <p className="activity-log__line is-search">웹 검색 중…</p> : null}
        {latestQuery ? <p className="activity-log__line is-search">🔍 {latestQuery}</p> : null}

        {entry.detail ? (
          <p className="activity-log__line is-summary">{entry.detail}</p>
        ) : streamTail ? (
          <p className="activity-log__line is-stream">{streamTail}</p>
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
  if (activity.entries.length === 0) {
    return null;
  }

  return (
    <section className="activity-log">
      <ul className="activity-log__rows">
        {activity.entries.map((entry, index) => (
          <EntryRow
            entry={entry}
            isLatest={index === activity.entries.length - 1}
            key={`${entry.id}-${index}`}
          />
        ))}
      </ul>
    </section>
  );
}
