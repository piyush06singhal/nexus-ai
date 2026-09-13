"use client";

/**
 * Minimal bearer-token persistence for the Phase 11 auth surface.
 *
 * Tokens are stored in localStorage (same pattern the ExternalShell uses for
 * the selected company). The API client attaches the access token only when it
 * is present; a missing token is fine because `auth_enabled` is off in
 * dev/test and the middleware otherwise returns a clear 401.
 */

const ACCESS_KEY = "nexus.accessToken";
const REFRESH_KEY = "nexus.refreshToken";
const SESSION_KEY = "nexus.sessionId";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(ACCESS_KEY);
}

export function storeSession(
  auth: { access_token: string; refresh_token: string; session_id: string },
): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(ACCESS_KEY, auth.access_token);
  window.localStorage.setItem(REFRESH_KEY, auth.refresh_token);
  window.localStorage.setItem(SESSION_KEY, auth.session_id);
}

export function clearSession(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(ACCESS_KEY);
  window.localStorage.removeItem(REFRESH_KEY);
  window.localStorage.removeItem(SESSION_KEY);
}