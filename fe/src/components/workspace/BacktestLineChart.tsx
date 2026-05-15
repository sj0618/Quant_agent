import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { BacktestPoint } from "../../types/quantagent";

export function BacktestLineChart({ series }: { series: BacktestPoint[] }) {
  return (
    <section className="panel-card chart-card">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Mock Backtest</span>
          <h2>수익률 곡선</h2>
        </div>
        <span className="pill pill--blue">Recharts</span>
      </div>
      <div className="chart-frame">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={series} margin={{ top: 16, right: 24, left: 0, bottom: 8 }} accessibilityLayer>
            <CartesianGrid stroke="#e2e8f0" strokeDasharray="4 6" vertical={false} />
            <XAxis dataKey="date" tickLine={false} axisLine={false} tick={{ fill: "#64748b", fontSize: 12 }} />
            <YAxis
              tickLine={false}
              axisLine={false}
              tick={{ fill: "#64748b", fontSize: 12 }}
              tickFormatter={(value: number) => `${value}`}
              width={42}
            />
            <Tooltip
              formatter={(value, name) => [`${Number(value).toFixed(1)}`, name === "strategy" ? "QuantAgent" : "KOSPI200"]}
              labelFormatter={(label) => `${label}`}
              contentStyle={{
                border: "1px solid #dbe4f0",
                borderRadius: "14px",
                boxShadow: "0 16px 40px rgba(15, 23, 42, 0.12)",
              }}
            />
            <Line type="monotone" dataKey="strategy" stroke="#2563eb" strokeWidth={3} dot={false} activeDot={{ r: 5 }} />
            <Line type="monotone" dataKey="benchmark" stroke="#94a3b8" strokeWidth={2} dot={false} strokeDasharray="5 5" />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
