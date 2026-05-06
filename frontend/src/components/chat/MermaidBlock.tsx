import { Check, Copy } from "lucide-react";
import mermaid from "mermaid";
import { useEffect, useMemo, useState } from "react";

interface Props {
  code: string;
}

let initialized = false;

function ensureMermaidInit() {
  if (initialized) return;
  mermaid.initialize({
    startOnLoad: false,
    theme: "dark",
    securityLevel: "loose",
  });
  initialized = true;
}

export default function MermaidBlock({ code }: Props) {
  const [svg, setSvg] = useState<string>("");
  const [error, setError] = useState<string>("");
  const [copied, setCopied] = useState(false);
  const graphId = useMemo(() => `mermaid-${Math.random().toString(36).slice(2)}`, []);

  useEffect(() => {
    let cancelled = false;

    const renderDiagram = async () => {
      try {
        ensureMermaidInit();
        const result = await mermaid.render(graphId, code);
        if (!cancelled) {
          setSvg(result.svg);
          setError("");
        }
      } catch (e) {
        if (!cancelled) {
          const msg = e instanceof Error ? e.message : "Failed to render diagram";
          setError(msg);
          setSvg("");
        }
      }
    };

    renderDiagram();
    return () => {
      cancelled = true;
    };
  }, [code, graphId]);

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="my-3 overflow-hidden rounded-xl border border-white/10 bg-slate-950/80">
      <div className="flex items-center justify-between border-b border-white/10 bg-white/5 px-3 py-1.5 text-xs">
        <span className="font-mono text-[11px] uppercase tracking-wider text-slate-400">diagram</span>
        <button
          onClick={onCopy}
          className="flex items-center gap-1 rounded px-2 py-0.5 text-slate-300 transition hover:bg-white/10 hover:text-white"
        >
          {copied ? (
            <>
              <Check className="h-3.5 w-3.5 text-emerald-400" /> Copied
            </>
          ) : (
            <>
              <Copy className="h-3.5 w-3.5" /> Copy
            </>
          )}
        </button>
      </div>

      {error ? (
        <div className="px-4 py-3 text-sm text-rose-300">
          <div className="mb-1 font-medium">Could not render graph</div>
          <pre className="whitespace-pre-wrap text-xs text-rose-200/90">{error}</pre>
        </div>
      ) : (
        <div className="overflow-x-auto px-2 py-2" dangerouslySetInnerHTML={{ __html: svg }} />
      )}
    </div>
  );
}
