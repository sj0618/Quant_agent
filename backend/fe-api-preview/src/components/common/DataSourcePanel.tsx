import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { getDataSourceEvents, subscribeDataSourceEvents, type DataSourceEvent } from "../../api/dataSourceClient";

const panelStyle = {
  position: "fixed",
  right: "16px",
  bottom: "16px",
  zIndex: 9999,
  maxWidth: "360px",
  borderRadius: "16px",
  border: "1px solid rgba(15, 23, 42, 0.16)",
  background: "rgba(255, 255, 255, 0.94)",
  boxShadow: "0 18px 50px rgba(15, 23, 42, 0.18)",
  color: "#0f172a",
  fontFamily: "system-ui, sans-serif",
  fontSize: "12px",
  overflow: "hidden",
} satisfies CSSProperties;

export function DataSourcePanel() {
  const [events, setEvents] = useState<DataSourceEvent[]>(() => getDataSourceEvents());
  const [open, setOpen] = useState(false);

  useEffect(() => subscribeDataSourceEvents(() => setEvents([...getDataSourceEvents()])), []);

  const counts = useMemo(
    () =>
      events.reduce(
        (acc, event) => ({ ...acc, [event.source]: acc[event.source] + 1 }),
        { server: 0, local: 0 },
      ),
    [events],
  );
  const latest = events[0];

  return (
    <aside aria-label="API data source monitor" style={panelStyle}>
      <button
        onClick={() => setOpen((current) => !current)}
        style={{
          alignItems: "center",
          background: "transparent",
          border: 0,
          color: "inherit",
          cursor: "pointer",
          display: "flex",
          gap: "10px",
          padding: "10px 12px",
          width: "100%",
        }}
        type="button"
      >
        <strong style={{ color: counts.local ? "#b45309" : "#047857" }}>
          API {counts.local ? "LOCAL" : "SERVER"}
        </strong>
        <span>server {counts.server}</span>
        <span>local {counts.local}</span>
      </button>
      {open ? (
        <div style={{ borderTop: "1px solid rgba(15, 23, 42, 0.1)", maxHeight: "260px", overflow: "auto", padding: "10px 12px" }}>
          <p style={{ margin: "0 0 8px" }}>
            화면 데이터가 backend에서 오면 <b>SERVER</b>, 브라우저 내부 상태를 읽으면 <b>LOCAL</b>입니다. 서버 오류는 fallback 없이 화면 오류로 노출됩니다.
          </p>
          {events.length ? (
            events.slice(0, 12).map((event) => (
              <div key={`${event.at}-${event.key}`} style={{ borderTop: "1px solid rgba(15, 23, 42, 0.08)", padding: "7px 0" }}>
                <b style={{ color: event.source === "server" ? "#047857" : "#b45309" }}>{event.source.toUpperCase()}</b>{" "}
                <span>{event.key}</span>
                <br />
                <code>{event.path}</code>
                {event.message ? <small style={{ display: "block" }}>{event.message}</small> : null}
              </div>
            ))
          ) : (
            <small>아직 API 호출 기록이 없습니다.</small>
          )}
          {latest ? <small>latest: {new Date(latest.at).toLocaleTimeString()}</small> : null}
        </div>
      ) : null}
    </aside>
  );
}
