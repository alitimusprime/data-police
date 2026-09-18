import { describe, it, expect, vi, afterEach } from 'vitest';
import { api, ApiError, formatNumber, human } from './api';
afterEach(() => vi.unstubAllGlobals());
describe('API boundary', () => {
  it('uses the same-origin session and required mutation header', async () => {
    const mock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ id: 1 }) });
    vi.stubGlobal('fetch', mock);
    await api('/rules', 'POST', { name: 'Test' });
    expect(mock).toHaveBeenCalledWith(
      '/api/rules',
      expect.objectContaining({
        credentials: 'same-origin',
        headers: expect.objectContaining({ 'X-DP-Request': '1' }),
        body: '{"name":"Test"}',
      }),
    );
  });
  it('does not hide errors behind successful data', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 422, json: async () => ({ detail: 'Invalid rule' }) }),
    );
    await expect(api('/rules')).rejects.toMatchObject({ status: 422, message: 'Invalid rule' });
  });
  it('uses a safe message for structured validation failures', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 422, json: async () => ({ detail: [{ msg: 'bad' }] }) }),
    );
    await expect(api('/rules')).rejects.toBeInstanceOf(ApiError);
  });
});
describe('display formatting', () => {
  it('does not fabricate values for unmeasured data', () => expect(formatNumber(null)).toBe('Not measured'));
  it('uses readable labels', () => expect(human('pipeline_failure')).toBe('pipeline failure'));
});
