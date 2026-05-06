import {
  BarChart,
  Bar,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

interface ChartPayload {
  type: "chart";
  chartType: "bar" | "line" | "pie";
  title: string;
  labels: string[];
  data: number[];
  xAxisLabel?: string;
  yAxisLabel?: string;
}

interface Props {
  payload: ChartPayload;
}

const COLORS = ["#8b5cf6", "#06b6d4", "#f59e0b", "#10b981", "#ef4444", "#ec4899"];

export default function ChartCard({ payload }: Props) {
  const rows = payload.labels.map((label, index) => ({
    label,
    value: Number(payload.data[index] ?? 0),
  }));
  
  // Dynamic width: larger base with more space per data point
  const minChartWidth = Math.max(1200, rows.length * 120);
  const isPie = payload.chartType === "pie";
  
  // Increased height for better visibility
  const chartHeight = isPie ? 500 : 600;

  return (
    <div className="my-3 rounded-xl border border-white/10 bg-slate-950/80 p-4">
      <div className="mb-3 text-sm font-semibold text-slate-100">{payload.title || "Chart"}</div>
      <div className="w-full overflow-x-auto rounded-lg border border-white/5 bg-slate-900/40 pb-2">
        <div
          className="w-full min-w-full"
          style={{ minWidth: isPie ? 700 : minChartWidth, height: chartHeight }}
        >
          <ResponsiveContainer width="100%" height="100%">
          {payload.chartType === "line" ? (
            <LineChart
              data={rows}
              margin={{ top: 20, right: 40, left: 60, bottom: 120 }}
            >
              <CartesianGrid stroke="rgba(255,255,255,0.08)" strokeDasharray="3 3" />
              <XAxis
                dataKey="label"
                stroke="#94a3b8"
                interval={Math.max(0, Math.floor(rows.length / 12))}
                angle={-45}
                textAnchor="end"
                height={110}
                tick={{ fontSize: 11, fill: "#cbd5e1" }}
                label={
                  payload.xAxisLabel
                    ? { value: payload.xAxisLabel, position: "insideBottomRight", offset: -10, fill: "#94a3b8", fontSize: 12 }
                    : undefined
                }
              />
              <YAxis
                stroke="#94a3b8"
                width={70}
                tick={{ fontSize: 11, fill: "#cbd5e1" }}
                label={
                  payload.yAxisLabel
                    ? { value: payload.yAxisLabel, angle: -90, position: "insideLeft", offset: 10, fill: "#94a3b8", fontSize: 12 }
                    : undefined
                }
              />
              <Tooltip contentStyle={{ backgroundColor: "rgba(15, 23, 42, 0.95)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8 }} />
              <Legend wrapperStyle={{ paddingTop: 16, fontSize: 12 }} />
              <Line type="monotone" dataKey="value" stroke="#8b5cf6" strokeWidth={3} dot={{ r: 5, fill: "#8b5cf6" }} activeDot={{ r: 7 }} />
            </LineChart>
          ) : payload.chartType === "pie" ? (
            <PieChart margin={{ top: 20, right: 60, left: 60, bottom: 20 }}>
              <Tooltip contentStyle={{ backgroundColor: "rgba(15, 23, 42, 0.95)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8 }} />
              <Legend wrapperStyle={{ paddingTop: 16, fontSize: 12 }} />
              <Pie data={rows} dataKey="value" nameKey="label" cx="45%" cy="50%" outerRadius={150} label={{ fontSize: 12, fill: "#cbd5e1" }}>
                {rows.map((entry, index) => (
                  <Cell key={`${entry.label}-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
            </PieChart>
          ) : (
            <BarChart
              data={rows}
              margin={{ top: 20, right: 40, left: 60, bottom: 120 }}
            >
              <CartesianGrid stroke="rgba(255,255,255,0.08)" strokeDasharray="3 3" />
              <XAxis
                dataKey="label"
                stroke="#94a3b8"
                interval={Math.max(0, Math.floor(rows.length / 12))}
                angle={-45}
                textAnchor="end"
                height={110}
                tick={{ fontSize: 11, fill: "#cbd5e1" }}
                label={
                  payload.xAxisLabel
                    ? { value: payload.xAxisLabel, position: "insideBottomRight", offset: -10, fill: "#94a3b8", fontSize: 12 }
                    : undefined
                }
              />
              <YAxis
                stroke="#94a3b8"
                width={70}
                tick={{ fontSize: 11, fill: "#cbd5e1" }}
                label={
                  payload.yAxisLabel
                    ? { value: payload.yAxisLabel, angle: -90, position: "insideLeft", offset: 10, fill: "#94a3b8", fontSize: 12 }
                    : undefined
                }
              />
              <Tooltip contentStyle={{ backgroundColor: "rgba(15, 23, 42, 0.95)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8 }} />
              <Legend wrapperStyle={{ paddingTop: 16, fontSize: 12 }} />
              <Bar dataKey="value" fill="#8b5cf6" radius={[6, 6, 0, 0]} />
            </BarChart>
          )}
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
