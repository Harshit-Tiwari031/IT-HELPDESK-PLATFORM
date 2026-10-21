import { afterEach, describe, expect, it, vi } from 'vitest';
import { clearCsrfToken, getAnalytics, getCurrentUser, login, logout, updateTicketStatus } from './api';

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), {
  status,
  headers: { 'Content-Type': 'application/json' },
});

describe('cookie authentication API client', () => {
  afterEach(() => {
    clearCsrfToken();
    vi.unstubAllGlobals();
  });

  it('gets a CSRF token before login and sends it with credentialed requests', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(json({ csrf_token: 'csrf-before-login' }))
      .mockResolvedValueOnce(json({ user: { id: '3d4c3b2a-1908-4f6e-9c7b-8a5d4e3f2c1b', login_identity: 'student@example.edu', role: 'user' }, csrf_token: 'csrf-session' }));
    vi.stubGlobal('fetch', fetchMock);

    const user = await login('student@example.edu', 'test-password');

    expect(user).toEqual({ id: '3d4c3b2a-1908-4f6e-9c7b-8a5d4e3f2c1b', login_identity: 'student@example.edu', role: 'user' });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ credentials: 'include' });
    expect(fetchMock.mock.calls[1][1]).toMatchObject({
      method: 'POST', credentials: 'include', body: JSON.stringify({ login_identity: 'student@example.edu', password: 'test-password' }),
    });
    expect(new Headers(fetchMock.mock.calls[1][1]?.headers).get('X-CSRF-Token')).toBe('csrf-before-login');
  });

  it('uses cookie credentials for identity lookup and protects logout with CSRF', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(json({ id: '3d4c3b2a-1908-4f6e-9c7b-8a5d4e3f2c1b', login_identity: 'student@example.edu', role: 'user' }))
      .mockResolvedValueOnce(json({ csrf_token: 'csrf-token' }))
      .mockResolvedValueOnce(json({ status: 'logged_out' }));
    vi.stubGlobal('fetch', fetchMock);

    await getCurrentUser();
    await logout();

    expect(fetchMock.mock.calls[0][1]).toMatchObject({ credentials: 'include' });
    expect(fetchMock.mock.calls[2][1]).toMatchObject({ method: 'POST', credentials: 'include' });
    expect(new Headers(fetchMock.mock.calls[2][1]?.headers).get('X-CSRF-Token')).toBe('csrf-token');
  });

  it('updates ticket status with cookie credentials and CSRF protection', async () => {
    const updatedTicket = {
      id: 'HD-1234ABCD', title: 'Wi-Fi connection issue', description: 'Disconnects during class.',
      category: 'Network', priority: 'High', status: 'Resolved', owner: 'student@example.edu',
      created_at: '2026-10-20T08:00:00Z', updated_at: '2026-10-20T09:00:00Z', resolved_at: '2026-10-20T09:00:00Z',
    };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(json({ csrf_token: 'csrf-ticket-status' }))
      .mockResolvedValueOnce(json(updatedTicket));
    vi.stubGlobal('fetch', fetchMock);

    const resolution = 'Updated the network driver and confirmed a stable connection.';
    const result = await updateTicketStatus('HD-1234ABCD', 'Resolved', resolution);

    expect(result.status).toBe('Resolved');
    expect(fetchMock.mock.calls[1][0]).toContain('/api/tickets/HD-1234ABCD');
    expect(fetchMock.mock.calls[1][1]).toMatchObject({ method: 'PATCH', credentials: 'include', body: JSON.stringify({ status: 'Resolved', resolution }) });
    expect(new Headers(fetchMock.mock.calls[1][1]?.headers).get('X-CSRF-Token')).toBe('csrf-ticket-status');
  });

  it('loads analytics from the admin API using the selected range and session cookie', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(json({
      days: 30, total_tickets: 2, resolved_tickets: 1, resolution_rate_percent: 50,
      average_first_response_minutes: null, tickets_with_workflow: 1,
      daily_volume: [], category_distribution: [{ category: 'Network', count: 2 }],
    }));
    vi.stubGlobal('fetch', fetchMock);

    const result = await getAnalytics(30);

    expect(result.total_tickets).toBe(2);
    expect(fetchMock.mock.calls[0][0]).toContain('/api/analytics?days=30');
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ credentials: 'include' });
  });
});
