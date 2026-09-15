"use client";

import { createContext, ReactNode, useContext, useMemo } from "react";
import { useAuth } from "@/components/auth-provider";

export type Persona = {
  email: string;
  role: "OWNER" | "ADMIN" | "MANAGER" | "EMPLOYEE";
  label: string;
};

type PersonaContextValue = {
  ready: boolean;
  persona: Persona;
  personas: Persona[];
  setPersona: (email: string) => void;
};

const PersonaContext = createContext<PersonaContextValue | null>(null);

const anonymousPersona: Persona = {
  email: "",
  role: "EMPLOYEE",
  label: "Guest",
};

export function PersonaProvider({ children }: { children: ReactNode }) {
  const { actor, ready } = useAuth();

  const value = useMemo(() => {
    if (!actor) {
      return {
        ready,
        persona: anonymousPersona,
        personas: [],
        setPersona: () => {},
      };
    }

    const persona = {
      email: actor.email,
      role: actor.role,
      label: actor.name ?? actor.email,
    } satisfies Persona;

    return {
      ready,
      persona,
      personas: [persona],
      setPersona: () => {},
    };
  }, [actor, ready]);

  return <PersonaContext.Provider value={value}>{children}</PersonaContext.Provider>;
}

export function usePersona() {
  const context = useContext(PersonaContext);
  if (!context) {
    throw new Error("usePersona must be used within PersonaProvider");
  }
  return context;
}

