interface TablePayload {
  type: "table";
  title: string;
  columns: string[];
  rows: Array<Array<string | number | boolean | null>>;
}

interface Props {
  payload: TablePayload;
}

export default function TableCard({ payload }: Props) {
  const columns = Array.isArray(payload.columns) ? payload.columns : [];
  const rows = Array.isArray(payload.rows) ? payload.rows : [];

  return (
    <div className="my-3 overflow-hidden rounded-xl border border-white/10 bg-slate-950/80 p-4">
      <div className="mb-3 text-sm font-semibold text-slate-100">{payload.title || "Table"}</div>
      <div className="w-full overflow-x-auto rounded-lg border border-white/10">
        <table className="w-full min-w-[520px] border-collapse text-sm">
          <thead className="bg-white/5">
            <tr>
              {columns.map((column, index) => (
                <th
                  key={`${column}-${index}`}
                  className="border border-white/20 px-3 py-2 text-left font-semibold text-slate-200"
                >
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rowIndex) => (
              <tr key={`row-${rowIndex}`}>
                {row.map((cell, cellIndex) => (
                  <td
                    key={`cell-${rowIndex}-${cellIndex}`}
                    className="border border-white/10 px-3 py-2 text-slate-200"
                  >
                    {cell === null ? "-" : String(cell)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
