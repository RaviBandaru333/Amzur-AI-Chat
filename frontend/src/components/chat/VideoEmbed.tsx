import { useMemo, useState } from "react";
import ReactPlayer from "react-player";

interface Props {
  url: string;
}

function isDirectVideoUrl(url: string) {
  return /\.(mp4|webm|ogg|mov|m4v)(\?|#|$)/i.test(url) || url.startsWith("data:video/");
}

function sanitizeUrl(raw: string) {
  return raw.trim().replace(/[)>.,;!?]+$/g, "").replace(/^<|>$/g, "");
}

function toHostedEmbedUrl(raw: string): string | null {
  const input = sanitizeUrl(raw);
  try {
    const parsed = new URL(input);
    const host = parsed.hostname.replace("www.", "").toLowerCase();

    if (host === "youtu.be") {
      const id = parsed.pathname.split("/").filter(Boolean)[0];
      return id ? `https://www.youtube-nocookie.com/embed/${id}` : null;
    }

    if (host === "youtube.com" || host === "m.youtube.com") {
      const videoId = parsed.searchParams.get("v");
      const listId = parsed.searchParams.get("list");
      if (videoId) return `https://www.youtube-nocookie.com/embed/${videoId}`;
      if (listId) return `https://www.youtube-nocookie.com/embed/videoseries?list=${listId}`;

      const parts = parsed.pathname.split("/").filter(Boolean);
      if (parts[0] === "shorts" && parts[1]) {
        return `https://www.youtube-nocookie.com/embed/${parts[1]}`;
      }
      if (parts[0] === "embed" && parts[1]) {
        return `https://www.youtube-nocookie.com/embed/${parts[1]}`;
      }
    }

    if (host === "vimeo.com" || host === "player.vimeo.com") {
      const parts = parsed.pathname.split("/").filter(Boolean);
      const id = parts[parts.length - 1];
      if (id && /^\d+$/.test(id)) {
        return `https://player.vimeo.com/video/${id}`;
      }
    }

    return null;
  } catch {
    return null;
  }
}

export default function VideoEmbed({ url }: Props) {
  const [hasError, setHasError] = useState(false);
  const cleanedUrl = useMemo(() => sanitizeUrl(url), [url]);
  const directFile = useMemo(() => isDirectVideoUrl(cleanedUrl), [cleanedUrl]);
  const hostedEmbedUrl = useMemo(() => toHostedEmbedUrl(cleanedUrl), [cleanedUrl]);

  if (hasError) {
    return (
      <div className="my-2 rounded-lg border border-amber-400/30 bg-amber-500/10 p-3 text-sm text-amber-100">
        <div className="font-medium">Inline playback is unavailable for this video source.</div>
        <a
          href={cleanedUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-1 inline-block text-accent-300 underline hover:text-accent-200"
        >
          Open video in new tab
        </a>
      </div>
    );
  }

  if (directFile) {
    return (
      <div className="my-2">
        <video
          controls
          preload="metadata"
          className="block w-full max-w-2xl rounded-lg border border-white/10 bg-black/60"
          onError={() => setHasError(true)}
        >
          <source src={cleanedUrl} />
          Your browser does not support the video tag.
        </video>
      </div>
    );
  }

  if (hostedEmbedUrl) {
    return (
      <div className="my-2">
        <div className="relative w-full max-w-2xl overflow-hidden rounded-lg border border-white/10 bg-black/60 pb-[56.25%]">
          <iframe
            src={hostedEmbedUrl}
            title="Embedded video"
            className="absolute left-0 top-0 h-full w-full"
            loading="lazy"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
            allowFullScreen
            onError={() => setHasError(true)}
          />
        </div>
        <a
          href={cleanedUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-1 inline-block text-xs text-accent-400 hover:text-accent-300 underline"
        >
          Open video in new tab
        </a>
      </div>
    );
  }

  return (
    <div className="my-2">
      <div className="relative w-full max-w-2xl overflow-hidden rounded-lg border border-white/10 bg-black/60 pb-[56.25%]">
        <ReactPlayer
          src={cleanedUrl}
          controls
          width="100%"
          height="100%"
          style={{ position: "absolute", inset: 0 }}
          onError={() => setHasError(true)}
        />
      </div>
      <a
        href={cleanedUrl}
        target="_blank"
        rel="noopener noreferrer"
        className="mt-1 inline-block text-xs text-accent-400 hover:text-accent-300 underline"
      >
        Open video in new tab
      </a>
    </div>
  );
}
