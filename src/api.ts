import type { Ticket } from './data';

// Match Vite's default localhost origin so SameSite=Lax cookies work in local development.
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/+$/, '');

type ApiTicket = Omit<Ticket, 'updated'> & { created_at: string; updated_at: string };
export type DashboardActivity = { workflow_id: string; ticket_id: string | null; stage: string; status: string; detail: string; created_at: string; simulated: boolean };
export type DashboardData = {
  open_tickets: number; in_progress_tickets: number; resolved_tickets: number; ai_verified_resolutions: number | null;
  priority_distribution: Record<'High' | 'Medium' | 'Low', number>;
  daily_volume: { date: string; created: number; resolved: number }[];
  recent_tickets: Ticket[]; ai_activity: DashboardActivity[];
};
export type AnalyticsData = {
  days: number;
  total_tickets: number;
  resolved_tickets: number;
  resolution_rate_percent: number | null;
  average_first_response_minutes: number | null;
  tickets_with_workflow: number;
  daily_volume: { date: string; created: number; resolved: number }[];
  category_distribution: { category: string; count: number }[];
};
export type TicketFilters = { search?: string; status?: string; priority?: string };
export type CreateTicketInput = Pick<Ticket, 'title' | 'description' | 'category' | 'priority'>;
export type AuthUser = { id: string; login_identity: string; role: 'user' | 'admin' };
export type AuthLoginResponse = { user: AuthUser; csrf_token: string };

export class ApiRequestError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiRequestError';
    this.status = status;
  }
}
export type ChatSource = { title: string; category: string };
export type ChatReply = { reply: string; source_articles: ChatSource[] };
export type WorkflowEvent = { stage: string; status: string; detail: string; evidence: Record<string, unknown>; created_at: string };
export type WorkflowRun = {
  id: string; issue: string; status: string; current_stage: string;
  diagnosis: { summary: string; category: string; suggested_priority: string; likely_causes: string[]; troubleshooting_steps: string[] };
  sources: ChatSource[]; tool_name: string; tool_input: Record<string, unknown>; tool_output: Record<string, unknown>;
  verification: { criterion: string; passed: boolean | null; reason: string; real_environment_verified: boolean; outcome: string };
  proposed_resolution: string; next_action: string; ticket_id: string | null; created_at: string; updated_at: string; events: WorkflowEvent[];
};

let csrfToken: string | null = null;

function relativeTime(value: string): string {
  const timestamp = new Date(value).getTime();
  if (Number.isNaN(timestamp)) return value;
  const seconds = Math.max(0, Math.floor((Date.now() - timestamp) / 1000));
  if (seconds < 60) return 'Just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} hour${Math.floor(seconds / 3600) === 1 ? '' : 's'} ago`;
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(timestamp);
}

function mapTicket(ticket: ApiTicket): Ticket {
  return { ...ticket, updated: relativeTime(ticket.updated_at) };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method || 'GET').toUpperCase();
  if (['POST', 'PATCH', 'PUT', 'DELETE'].includes(method) && !csrfToken && path !== '/api/auth/login') {
    await fetchCsrfToken();
  }
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  if (['POST', 'PATCH', 'PUT', 'DELETE'].includes(method) && csrfToken) headers.set('X-CSRF-Token', csrfToken);
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      credentials: 'include',
      headers,
    });
  } catch {
    throw new Error(`Cannot reach the Helpdesk API at ${API_BASE_URL}. Start the FastAPI backend and check VITE_API_BASE_URL.`);
  }

  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: unknown } | null;
    const detail = Array.isArray(body?.detail)
      ? body.detail.map((issue: { msg?: string; loc?: (string | number)[] }) => `${issue.loc?.slice(1).join('.') || 'Request'}: ${issue.msg || 'invalid value'}`).join(' ')
      : typeof body?.detail === 'string' ? body.detail
      : body?.detail && typeof body.detail === 'object' && 'message' in body.detail
        ? `${String((body.detail as { message: unknown }).message)}${'code' in body.detail ? ` [${String((body.detail as { code: unknown }).code)}]` : ''}`
        : `Request failed (${response.status}).`;
    throw new ApiRequestError(detail, response.status);
  }

  return response.json() as Promise<T>;
}

export async function fetchCsrfToken(): Promise<string> {
  const data = await request<{ csrf_token: string }>('/api/auth/csrf');
  csrfToken = data.csrf_token;
  return csrfToken;
}

export async function login(login_identity: string, password: string): Promise<AuthUser> {
  const token = await fetchCsrfToken();
  const result = await request<AuthLoginResponse>('/api/auth/login', {
    method: 'POST',
    headers: { 'X-CSRF-Token': token },
    body: JSON.stringify({ login_identity, password }),
  });
  csrfToken = result.csrf_token;
  return result.user;
}

export async function getCurrentUser(): Promise<AuthUser> {
  return request<AuthUser>('/api/auth/me');
}

export async function logout(): Promise<void> {
  if (!csrfToken) await fetchCsrfToken();
  await request<{ status: string }>('/api/auth/logout', { method: 'POST' });
  csrfToken = null;
}

export function clearCsrfToken(): void {
  csrfToken = null;
}

export async function listTickets(filters: TicketFilters = {}, signal?: AbortSignal): Promise<Ticket[]> {
  const params = new URLSearchParams();
  if (filters.search?.trim()) params.set('search', filters.search.trim());
  if (filters.status) params.set('status', filters.status);
  if (filters.priority) params.set('priority', filters.priority);
  const query = params.size ? `?${params.toString()}` : '';
  const result = await request<ApiTicket[]>(`/api/tickets${query}`, { signal });
  return result.map(mapTicket);
}

export async function getDashboard(days: number, signal?: AbortSignal): Promise<DashboardData> {
  const data = await request<Omit<DashboardData, 'recent_tickets'> & { recent_tickets: ApiTicket[] }>(`/api/dashboard?days=${encodeURIComponent(days)}`, { signal });
  return { ...data, recent_tickets: data.recent_tickets.map(mapTicket) };
}

export async function getAnalytics(days: number, signal?: AbortSignal): Promise<AnalyticsData> {
  return request<AnalyticsData>(`/api/analytics?days=${encodeURIComponent(days)}`, { signal });
}

export async function getTicket(ticketId: string): Promise<Ticket> {
  return mapTicket(await request<ApiTicket>(`/api/tickets/${encodeURIComponent(ticketId)}`));
}

export async function updateTicketStatus(ticketId: string, status: Ticket['status'], resolution?: string): Promise<Ticket> {
  return mapTicket(await request<ApiTicket>(`/api/tickets/${encodeURIComponent(ticketId)}`, {
    method: 'PATCH',
    body: JSON.stringify({ status, ...(resolution ? { resolution } : {}) }),
  }));
}

export async function createTicket(input: CreateTicketInput): Promise<Ticket> {
  return mapTicket(await request<ApiTicket>('/api/tickets', { method: 'POST', body: JSON.stringify(input) }));
}

export async function sendAssistantMessage(issue: string): Promise<ChatReply> {
  return request<ChatReply>('/api/ai/chat', { method: 'POST', body: JSON.stringify({ issue }) });
}

export async function createWorkflow(issue: string, ticketId?: string): Promise<WorkflowRun> {
  return request<WorkflowRun>('/api/workflows', { method: 'POST', body: JSON.stringify({ issue, ...(ticketId ? { ticket_id: ticketId } : {}) }) });
}

export async function listWorkflows(): Promise<WorkflowRun[]> {
  return request<WorkflowRun[]>('/api/workflows');
}

export async function confirmWorkflow(id: string, fixed: boolean): Promise<WorkflowRun> {
  return request<WorkflowRun>(`/api/workflows/${encodeURIComponent(id)}/confirm`, { method: 'POST', body: JSON.stringify({ fixed }) });
}
