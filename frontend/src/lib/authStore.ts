import { create } from "zustand";
import type { User } from "../types";
import { api } from "./api";
import { useChatStore } from "./chatStore";

interface AuthState {
  user: User | null;
  loading: boolean;
  error: string | null;
  checkSession: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName?: string) => Promise<void>;
  logout: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  loading: true,
  error: null,

  checkSession: async () => {
    set({ loading: true, error: null });
    try {
      const user = await api.me();
      set({ user, loading: false });
    } catch {
      set({ user: null, loading: false });
    }
  },

  login: async (email, password) => {
    set({ loading: true, error: null });
    try {
      const user = await api.login(email, password);
      // Fresh session: clear any chat state from a previous user on this device.
      useChatStore.getState().reset();
      set({ user, loading: false });
    } catch (e) {
      set({ loading: false, error: e instanceof Error ? e.message : "Login failed" });
      throw e;
    }
  },

  register: async (email, password, fullName) => {
    set({ loading: true, error: null });
    try {
      await api.register(email, password, fullName);
      // Do NOT auto-login — user must sign in explicitly after registering.
      set({ loading: false });
    } catch (e) {
      set({ loading: false, error: e instanceof Error ? e.message : "Registration failed" });
      throw e;
    }
  },

  logout: async () => {
    await api.logout().catch(() => {});
    useChatStore.getState().reset();
    set({ user: null });
  },
}));
