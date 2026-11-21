export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function j<T = any>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${API}${path}`, { ...init, headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) } });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail ?? `HTTP ${r.status}`);
  return body as T;
}
