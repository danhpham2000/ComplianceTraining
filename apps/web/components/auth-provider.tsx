"use client";

import { createContext, ReactNode, useContext, useEffect, useMemo, useState } from "react";
import { API_BASE } from "@/lib/api";
import { clearStoredToken, getStoredToken, setStoredToken } from "@/lib/auth-storage";
import { Actor, AuthSession } from "@/lib/types";

type AuthContextValue = {
  actor: Actor | null;
  ready: boolean;
  token: string | null;
  signIn: (session: AuthSession) => void;
  signOut: () => Promise<void>;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [actor, setActor] = useState<Actor | null>(null);
  const [token, setToken] = useState<string | null>(() => getStoredToken());
  const [ready, setReady] = useState(() => getStoredToken() == null);

  useEffect(() => {
    if (!token) {
      return;
    }

    void fetch(`${API_BASE}/auth/me`, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error("Session expired");
        }
        const nextActor = (await response.json()) as Actor;
        setActor(nextActor);
      })
      .catch(() => {
        clearStoredToken();
        setToken(null);
        setActor(null);
      })
      .finally(() => {
        setReady(true);
      });
  }, [token]);

  const value = useMemo<AuthContextValue>(
    () => ({
      actor,
      ready,
      token,
      signIn: (session) => {
        setStoredToken(session.token);
        setToken(session.token);
        setActor(session.actor);
      },
      signOut: async () => {
        const currentToken = getStoredToken();
        if (currentToken) {
          try {
            await fetch(`${API_BASE}/auth/logout`, {
              method: "POST",
              headers: {
                Authorization: `Bearer ${currentToken}`,
              },
            });
          } catch {
            // Ignore logout network failures and clear the local session regardless.
          }
        }
        clearStoredToken();
        setToken(null);
        setActor(null);
      },
      refresh: async () => {
        const currentToken = getStoredToken();
        if (!currentToken) {
          setActor(null);
          return;
        }
        const response = await fetch(`${API_BASE}/auth/me`, {
          headers: {
            Authorization: `Bearer ${currentToken}`,
          },
        });
        if (!response.ok) {
          clearStoredToken();
          setToken(null);
          setActor(null);
          return;
        }
        setToken(currentToken);
        setActor((await response.json()) as Actor);
      },
    }),
    [actor, ready, token],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
