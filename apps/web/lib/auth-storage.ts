const TOKEN_KEY = "nextphase.auth.token";
const PENDING_KEY = "nextphase.auth.pending";

type PendingVerificationState = {
  email: string;
  verificationCodeHint?: string | null;
};

function isBrowser() {
  return typeof window !== "undefined";
}

export function getStoredToken() {
  if (!isBrowser()) {
    return null;
  }
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setStoredToken(token: string) {
  if (!isBrowser()) {
    return;
  }
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearStoredToken() {
  if (!isBrowser()) {
    return;
  }
  window.localStorage.removeItem(TOKEN_KEY);
}

export function setPendingVerification(state: PendingVerificationState) {
  if (!isBrowser()) {
    return;
  }
  window.sessionStorage.setItem(PENDING_KEY, JSON.stringify(state));
}

export function getPendingVerification(): PendingVerificationState | null {
  if (!isBrowser()) {
    return null;
  }
  const raw = window.sessionStorage.getItem(PENDING_KEY);
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw) as PendingVerificationState;
  } catch {
    return null;
  }
}

export function clearPendingVerification() {
  if (!isBrowser()) {
    return;
  }
  window.sessionStorage.removeItem(PENDING_KEY);
}

