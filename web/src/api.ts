export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
export async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch('/api' + path, {
    method,
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      'X-DP-Request': '1',
      ...(method === 'POST' && path === '/runs' ? { 'Idempotency-Key': crypto.randomUUID() } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw new ApiError(
      response.status,
      typeof data.detail === 'string' ? data.detail : 'Please check the values and try again.',
    );
  }
  return response.json();
}
export const formatNumber = (n: number | null | undefined) =>
  n == null ? 'Not measured' : new Intl.NumberFormat('en', { maximumFractionDigits: 1 }).format(n);
export const dateTime = (value: string | null | undefined) =>
  value
    ? new Date(value).toLocaleString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    : 'No materialization';
export const clock = (value: string) =>
  new Date(value).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' });
export const human = (text: string) => text.replaceAll('_', ' ');
