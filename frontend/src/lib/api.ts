// Backend API client. All HTTP lives here; components/pages call `api.*`.
import type {
  ChatMessage,
  ChatResponse,
  HealthResponse,
  Note,
  Thread,
  ThreadDetail,
  ChatMode,
  UploadedFileAsset,
  User,
} from "../types";

const CONFIGURED_API_BASE = import.meta.env.VITE_API_BASE as string | undefined;
const API_BASE_CANDIDATES = [
  CONFIGURED_API_BASE,
  "http://localhost:8000",
  "http://127.0.0.1:8001",
].filter((v, i, arr): v is string => Boolean(v) && arr.indexOf(v) === i);
const REQUEST_TIMEOUT_MS = 7000;

async function fetchWithTimeout(url: string, init?: RequestInit): Promise<Response> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    return await fetch(url, {
      ...init,
      signal: controller.signal,
    });
  } finally {
    window.clearTimeout(timer);
  }
}

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  let lastNetworkError: unknown = null;

  for (const base of API_BASE_CANDIDATES) {
    try {
      const res = await fetchWithTimeout(`${base}${path}`, {
        credentials: "include",
        headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
        ...init,
      });
      if (!res.ok) {
        if (res.status === 401) throw new Error("UNAUTHORIZED");
        const text = await res.text();
        throw new Error(`${res.status} ${res.statusText}: ${text}`);
      }
      return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      const isNetworkIssue =
        message.includes("Failed to fetch") ||
        message.includes("NetworkError") ||
        message.includes("aborted") ||
        message.includes("AbortError");
      if (!isNetworkIssue) {
        throw err;
      }
      lastNetworkError = err;
    }
  }

  throw (lastNetworkError instanceof Error
    ? lastNetworkError
    : new Error("Unable to reach backend API"));
}

export const api = {
  // Health
  health: () => http<HealthResponse>("/api/health"),

  // Models
  getAvailableModels: () =>
    http<{ data: Array<{ id: string; name: string; provider: string }> }>("/api/models"),

  // Auth
  register: (email: string, password: string, full_name?: string) =>
    http<User>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, full_name }),
    }),
  login: (email: string, password: string) =>
    http<User>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  logout: () => http<{ ok: boolean }>("/api/auth/logout", { method: "POST" }),
  me: () => http<User>("/api/auth/me"),
  googleLoginUrl: () => `${API_BASE_CANDIDATES[0] ?? "http://localhost:8000"}/api/auth/google/login`,

  // Threads
  listThreads: () => http<Thread[]>("/api/threads"),
  createThread: (title?: string) =>
    http<Thread>("/api/threads", {
      method: "POST",
      body: JSON.stringify({ title }),
    }),
  getThread: (id: string) => http<ThreadDetail>(`/api/threads/${id}`),
  renameThread: (id: string, title: string) =>
    http<Thread>(`/api/threads/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    }),
  deleteThread: (id: string) =>
    http<void>(`/api/threads/${id}`, { method: "DELETE" }),
  sendMessage: (threadId: string, content: string, model?: string, mode: ChatMode = "chat") =>
    http<ThreadDetail>(`/api/threads/${threadId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content, model, mode }),
    }),
  editMessage: (
    threadId: string,
    messageId: string,
    content: string,
    model?: string,
    mode: ChatMode = "chat"
  ) =>
    http<ThreadDetail>(`/api/threads/${threadId}/messages/${messageId}`, {
      method: "PATCH",
      body: JSON.stringify({ content, model, mode }),
    }),
  uploadFiles: async (files: File[]) => {
    const form = new FormData();
    for (const file of files) {
      form.append("files", file);
    }

    let lastNetworkError: unknown = null;

    for (const base of API_BASE_CANDIDATES) {
      try {
        const res = await fetchWithTimeout(`${base}/api/files/upload`, {
          method: "POST",
          credentials: "include",
          body: form,
        });
        if (!res.ok) {
          if (res.status === 401) throw new Error("UNAUTHORIZED");
          const text = await res.text();
          throw new Error(`${res.status} ${res.statusText}: ${text}`);
        }
        const body = (await res.json()) as { files: UploadedFileAsset[] };
        return body.files;
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        const isNetworkIssue =
          message.includes("Failed to fetch") ||
          message.includes("NetworkError") ||
          message.includes("aborted") ||
          message.includes("AbortError");
        if (!isNetworkIssue) {
          throw err;
        }
        lastNetworkError = err;
      }
    }

    throw (lastNetworkError instanceof Error
      ? lastNetworkError
      : new Error("Unable to reach backend API"));
  },

  // Notes
  listNotes: () => http<Note[]>("/api/notes"),
  createNote: (title: string, content: string) =>
    http<Note>("/api/notes", { method: "POST", body: JSON.stringify({ title, content }) }),
  deleteNote: (id: number) => http<void>(`/api/notes/${id}`, { method: "DELETE" }),
  summarize: (id: number) =>
    http<{ note_id: number; summary: string }>("/api/summarize", {
      method: "POST",
      body: JSON.stringify({ note_id: id }),
    }),

  // Simple chat (no thread, no auth — P1 fallback)
  chat: (messages: ChatMessage[]) =>
    http<ChatResponse>("/api/chat", { method: "POST", body: JSON.stringify({ messages }) }),
};

