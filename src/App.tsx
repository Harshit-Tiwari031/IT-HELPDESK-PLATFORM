import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { Activity, ArrowDownRight, ArrowUpRight, Bell, BookOpen, Bot, Check, ChevronDown, ChevronRight, CircleHelp, Clock3, Command, FilePlus2, Filter, Headphones, Home, LifeBuoy, LoaderCircle, LockKeyhole, Menu, MoreHorizontal, Network, Plus, Search, Send, Settings, Sparkles, Ticket as TicketIcon, TrendingUp, X } from 'lucide-react';
import { ApiRequestError, clearCsrfToken, confirmWorkflow, createTicket as postTicket, createWorkflow, getAnalytics, getCurrentUser, getDashboard, getTicket as fetchTicket, listTickets, listWorkflows, login as loginRequest, logout as logoutRequest, sendAssistantMessage, updateTicketStatus, type AnalyticsData, type AuthUser, type ChatSource, type DashboardData, type WorkflowRun } from './api';
import { ChatMarkdown } from './components/ChatMarkdown';
import { LoginPage } from './components/LoginPage';
import { workflowViewState } from './workflowViewState';
import { articles, type Ticket } from './data';
import './App.css';
import './api.css';
import './auth.css';
import './theme.css';

type Page = 'Dashboard' | 'AI Help Center' | 'Tickets' | 'Agentic Workflow Monitor' | 'Knowledge Base' | 'Analytics' | 'Settings';
type ChatMessage = { text: string; from: 'bot' | 'user'; provider?: 'welcome' | 'groq'; sources?: ChatSource[] };
const navigation: { name: Page; icon: typeof Home }[] = [
  { name: 'Dashboard', icon: Home }, { name: 'AI Help Center', icon: Sparkles }, { name: 'Tickets', icon: TicketIcon }, { name: 'Agentic Workflow Monitor', icon: Activity }, { name: 'Knowledge Base', icon: BookOpen }, { name: 'Analytics', icon: TrendingUp },
];

function StatusBadge({ value }: { value: string }) { return <span className={`badge badge-${value.toLowerCase().replaceAll(' ', '-')}`}><i />{value}</span>; }
function PriorityBadge({ value }: { value: string }) { return <span className={`priority priority-${value.toLowerCase()}`}><i />{value}</span>; }

function App() {
  const [authStatus, setAuthStatus] = useState<'loading' | 'signed-out' | 'signed-in'>('loading');
  const [authUser, setAuthUser] = useState<AuthUser | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);
  const [authBusy, setAuthBusy] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const [page, setPage] = useState<Page>('Dashboard');
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [ticketLoading, setTicketLoading] = useState(true);
  const [ticketError, setTicketError] = useState<string | null>(null);
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [dashboardLoading, setDashboardLoading] = useState(false);
  const [dashboardError, setDashboardError] = useState<string | null>(null);
  const dashboardDays = 7;
  const [dashboardReload, setDashboardReload] = useState(0);
  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);
  const [analyticsDays, setAnalyticsDays] = useState(30);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);
  const [analyticsError, setAnalyticsError] = useState<string | null>(null);
  const [analyticsReload, setAnalyticsReload] = useState(0);
  const [ticketDetailLoading, setTicketDetailLoading] = useState(false);
  const [ticketDetailError, setTicketDetailError] = useState<string | null>(null);
  const [ticketStatusSaving, setTicketStatusSaving] = useState(false);
  const [ticketStatusError, setTicketStatusError] = useState<string | null>(null);
  const [ticketResolution, setTicketResolution] = useState('');
  const [ticketCreateLoading, setTicketCreateLoading] = useState(false);
  const [ticketCreateError, setTicketCreateError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [ticketQuery, setTicketQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('All statuses');
  const [priorityFilter, setPriorityFilter] = useState('All priorities');
  const [showCreate, setShowCreate] = useState(false);
  const [selectedTicket, setSelectedTicket] = useState<Ticket | null>(null);
  const createDialogRef = useRef<HTMLFormElement>(null);
  const ticketDetailDialogRef = useRef<HTMLDivElement>(null);
  const ticketDialogOpen = selectedTicket !== null;
  const [articleFilter, setArticleFilter] = useState('All articles');
  const [articleQuery, setArticleQuery] = useState('');
  const [selectedArticle, setSelectedArticle] = useState<number | null>(null);
  const [mobileMenu, setMobileMenu] = useState(false);
  const [message, setMessage] = useState('');
  const [lastChatIssue, setLastChatIssue] = useState('');
  const [chat, setChat] = useState<ChatMessage[]>([{ from: 'bot', provider: 'welcome', text: "Hello! I'm your IT support assistant. Tell me what's going on, and I'll help you find a solution or connect you with the right team." }]);
  const [chatSending, setChatSending] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const [workflowRuns, setWorkflowRuns] = useState<WorkflowRun[]>([]);
  const [workflowLoading, setWorkflowLoading] = useState(true);
  const [workflowError, setWorkflowError] = useState<string | null>(null);
  const [workflowStartLoading, setWorkflowStartLoading] = useState(false);
  const [workflowStartError, setWorkflowStartError] = useState<string | null>(null);
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<string | null>(null);
  const [workflowConfirming, setWorkflowConfirming] = useState(false);
  const [notificationOpen, setNotificationOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);

  useEffect(() => {
    let active = true;
    void getCurrentUser().then((user) => {
      if (!active) return;
      setAuthUser(user);
      setAuthStatus('signed-in');
      setAuthError(null);
    }).catch((error: unknown) => {
      if (!active) return;
      setAuthUser(null);
      setAuthStatus('signed-out');
      setAuthError(error instanceof ApiRequestError && error.status === 401 ? null : 'Could not verify your session. Sign in again or check that the Helpdesk server is available.');
    });
    return () => { active = false; };
  }, []);

  const handleLogin = async (identity: string, password: string) => {
    setAuthBusy(true);
    setAuthError(null);
    try {
      const user = await loginRequest(identity, password);
      setAuthUser(user);
      setAuthStatus('signed-in');
      setPage('Dashboard');
      setTickets([]); setDashboard(null); setWorkflowRuns([]); setSelectedWorkflowId(null);
    } catch (error) {
      const message = error instanceof Error ? error.message : '';
      setAuthError(message.includes('Cannot reach') ? 'The Helpdesk server is unavailable. Please try again when it is running.' : null);
      throw error;
    } finally {
      setAuthBusy(false);
    }
  };

  const handleLogout = async () => {
    setLogoutError(null);
    setAuthBusy(true);
    try {
      await logoutRequest();
      clearCsrfToken();
      setAuthUser(null); setAuthStatus('signed-out'); setPage('Dashboard');
      setTickets([]); setDashboard(null); setWorkflowRuns([]); setSelectedWorkflowId(null);
      setSelectedTicket(null); setChat([{ from: 'bot', provider: 'welcome', text: 'Hello! I am your IT support assistant. Describe your issue to get started.' }]);
      setMobileMenu(false); setProfileOpen(false);
    } catch {
      setLogoutError('Could not end the server session. Check your connection and try again.');
    } finally {
      setAuthBusy(false);
    }
  };

  const loadTickets = useCallback(async (signal?: AbortSignal) => {
    if (authStatus !== 'signed-in') return;
    try {
      const filters = page === 'Tickets' ? {
        search: ticketQuery,
        status: statusFilter === 'All statuses' ? undefined : statusFilter,
        priority: priorityFilter === 'All priorities' ? undefined : priorityFilter,
      } : {};
      setTickets(await listTickets(filters, signal));
    } catch (error) {
      if (signal?.aborted) return;
      setTicketError(error instanceof Error ? error.message : 'Could not load tickets.');
    } finally {
      if (!signal?.aborted) setTicketLoading(false);
    }
  }, [page, ticketQuery, statusFilter, priorityFilter, authStatus]);

  useEffect(() => {
    if (authStatus !== 'signed-in') return;
    if (page !== 'Dashboard' && page !== 'Tickets') return;
    const controller = new AbortController();
    // eslint-disable-next-line react/set-state-in-effect -- fetch state is updated asynchronously from the external API request.
    void loadTickets(controller.signal);
    return () => controller.abort();
  }, [loadTickets, page, authStatus]);

  useEffect(() => {
    if (authStatus !== 'signed-in') return;
    if (page !== 'Dashboard') return;
    if (authUser?.role === 'admin') return;
    const controller = new AbortController();
    setDashboardLoading(true);
    setDashboardError(null);
    setDashboard(null);
    void getDashboard(dashboardDays, controller.signal).then(setDashboard).catch((error: unknown) => {
      if (!controller.signal.aborted) setDashboardError(error instanceof Error ? error.message : 'Could not load dashboard data.');
    }).finally(() => {
      if (!controller.signal.aborted) setDashboardLoading(false);
    });
    return () => controller.abort();
  }, [dashboardDays, dashboardReload, page, authStatus, authUser?.role]);

  useEffect(() => {
    if (authStatus !== 'signed-in' || page !== 'Analytics' || authUser?.role !== 'admin') return;
    const controller = new AbortController();
    // eslint-disable-next-line react/set-state-in-effect -- reflect the pending analytics API request.
    setAnalyticsLoading(true);
    setAnalyticsError(null);
    setAnalytics(null);
    void getAnalytics(analyticsDays, controller.signal).then(setAnalytics).catch((error: unknown) => {
      if (!controller.signal.aborted) setAnalyticsError(error instanceof Error ? error.message : 'Could not load analytics.');
    }).finally(() => {
      if (!controller.signal.aborted) setAnalyticsLoading(false);
    });
    return () => controller.abort();
  }, [analyticsDays, analyticsReload, authStatus, authUser?.role, page]);

  const refreshWorkflows = useCallback(async () => {
    if (authStatus !== 'signed-in') return;
    setWorkflowLoading(true);
    setWorkflowError(null);
    try {
      const runs = await listWorkflows();
      setWorkflowRuns(runs);
      setSelectedWorkflowId((current) => current && runs.some((run) => run.id === current) ? current : runs[0]?.id ?? null);
    } catch (error) {
      setWorkflowError(error instanceof Error ? error.message : 'Could not load workflow runs.');
    } finally {
      setWorkflowLoading(false);
    }
  }, [authStatus]);

  useEffect(() => {
    if (authStatus === 'signed-in' && page === 'Agentic Workflow Monitor') void refreshWorkflows();
  }, [page, refreshWorkflows, authStatus]);

  useEffect(() => {
    const dialog = showCreate ? createDialogRef.current : ticketDialogOpen ? ticketDetailDialogRef.current : null;
    if (!dialog) return;
    const previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const firstFocusable = dialog.querySelector<HTMLElement>('input:not([disabled])') ?? dialog.querySelector<HTMLElement>('select:not([disabled]), textarea:not([disabled]), button:not([disabled]), [tabindex]:not([tabindex="-1"])');
    (firstFocusable ?? dialog).focus();
    return () => {
      if (previouslyFocused?.isConnected) previouslyFocused.focus();
    };
  }, [showCreate, ticketDialogOpen]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const dialog = document.querySelector<HTMLElement>('[aria-modal="true"]');
      if (dialog && event.key === 'Tab') {
        const focusable = [...dialog.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')];
        if (focusable.length === 0) {
          event.preventDefault();
          dialog.focus();
        } else if (event.shiftKey && document.activeElement === focusable[0]) {
          event.preventDefault();
          focusable[focusable.length - 1].focus();
        } else if (!event.shiftKey && document.activeElement === focusable[focusable.length - 1]) {
          event.preventDefault();
          focusable[0].focus();
        }
      }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        document.getElementById('global-search')?.focus();
      }
      if (event.key === 'Escape') {
        setShowCreate(false);
        setSelectedTicket(null);
        setQuery('');
        setNotificationOpen(false);
        setProfileOpen(false);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  const filteredArticles = useMemo(() => articles.map((a, index) => ({ ...a, index })).filter((a) => `${a.title} ${a.category} ${a.intro}`.toLowerCase().includes(articleQuery.toLowerCase()) && (articleFilter === 'All articles' || a.category === articleFilter)), [articleQuery, articleFilter]);
  const globalResults = useMemo(() => {
    if (!query.trim()) return [];
    return [...tickets.filter((t) => `${t.title} ${t.id} ${t.category}`.toLowerCase().includes(query.toLowerCase())).slice(0, 3).map((t) => ({ label: t.title, sub: t.id, page: 'Tickets' as Page })), ...articles.filter((a) => a.title.toLowerCase().includes(query.toLowerCase())).slice(0, 2).map((a) => ({ label: a.title, sub: 'Knowledge Base', page: 'Knowledge Base' as Page }))];
  }, [tickets, query]);

  const createTicket = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setTicketCreateLoading(true);
    setTicketCreateError(null);
    try {
      const newTicket = await postTicket({
        title: String(form.get('title')),
        category: String(form.get('category')),
        priority: String(form.get('priority')) as Ticket['priority'],
        description: String(form.get('description')),
      });
      setTickets((current) => [newTicket, ...current.filter((ticket) => ticket.id !== newTicket.id)]);
      setShowCreate(false);
      setPage('Tickets');
      setTicketError(null);
      setTicketQuery('');
      setStatusFilter('All statuses');
      setPriorityFilter('All priorities');
      setSelectedTicket(newTicket);
      setTicketDetailError(null);
    } catch (error) {
      setTicketCreateError(error instanceof Error ? error.message : 'The ticket could not be created.');
    } finally {
      setTicketCreateLoading(false);
    }
  };

  const openTicket = async (ticket: Ticket) => {
    setSelectedTicket(ticket);
    setTicketDetailLoading(true);
    setTicketDetailError(null);
    setTicketStatusError(null);
    setTicketResolution('');
    try {
      const detail = await fetchTicket(ticket.id);
      setSelectedTicket(detail);
      setTickets((current) => current.map((item) => item.id === detail.id ? detail : item));
    } catch (error) {
      setTicketDetailError(error instanceof Error ? error.message : 'The ticket details could not be loaded.');
    } finally {
      setTicketDetailLoading(false);
    }
  };

  const changeTicketStatus = async (status: Ticket['status'], resolution?: string) => {
    if (!selectedTicket || authUser?.role !== 'admin' || ticketStatusSaving) return;
    if (status === 'Resolved' && (resolution?.trim().length ?? 0) < 10) {
      setTicketStatusError('Describe the fix in at least 10 characters before resolving this ticket.');
      return;
    }
    setTicketStatusSaving(true);
    setTicketStatusError(null);
    try {
      const updated = await updateTicketStatus(selectedTicket.id, status, resolution?.trim());
      setSelectedTicket(updated);
      setTickets((current) => current.map((item) => item.id === updated.id ? updated : item));
      setTicketResolution('');
      setDashboardReload((current) => current + 1);
    } catch (error) {
      setTicketStatusError(error instanceof Error ? error.message : 'The ticket status could not be updated.');
    } finally {
      setTicketStatusSaving(false);
    }
  };

  const sendMessage = async (text = message) => {
    const value = text.trim();
    if (!value || chatSending) return;
    setLastChatIssue(value);
    setChat((current) => [...current, { from: 'user', text: value }]);
    setMessage('');
    setChatError(null);
    setChatSending(true);
    try {
      const answer = await sendAssistantMessage(value);
      setChat((current) => [...current, { from: 'bot', provider: 'groq', text: answer.reply, sources: answer.source_articles }]);
    } catch (error) {
      setChatError(error instanceof Error ? error.message : 'Groq is unavailable. Please retry or create a support ticket.');
    } finally {
      setChatSending(false);
    }
  };

  const startWorkflow = async (text = message.trim() || lastChatIssue) => {
    const issue = text.trim();
    if (issue.length < 5 || workflowStartLoading) return;
    setWorkflowStartLoading(true);
    setWorkflowStartError(null);
    try {
      const run = await createWorkflow(issue);
      setWorkflowRuns((current) => [run, ...current.filter((item) => item.id !== run.id)]);
      setSelectedWorkflowId(run.id);
      setPage('Agentic Workflow Monitor');
      setMobileMenu(false);
    } catch (error) {
      setWorkflowStartError(error instanceof Error ? error.message : 'The troubleshooting workflow could not be started.');
    } finally {
      setWorkflowStartLoading(false);
    }
  };

  const confirmSelectedWorkflow = async (fixed: boolean) => {
    const run = workflowRuns.find((item) => item.id === selectedWorkflowId);
    if (!run || workflowConfirming) return;
    setWorkflowConfirming(true);
    setWorkflowError(null);
    try {
      const updated = await confirmWorkflow(run.id, fixed);
      setWorkflowRuns((current) => current.map((item) => item.id === updated.id ? updated : item));
    } catch (error) {
      setWorkflowError(error instanceof Error ? error.message : 'Your confirmation could not be saved.');
    } finally {
      setWorkflowConfirming(false);
    }
  };

  const makePage = (name: Page) => { if (name === 'Agentic Workflow Monitor') { setWorkflowLoading(true); setWorkflowError(null); } setPage(name); setMobileMenu(false); setQuery(''); setTicketLoading(true); setTicketError(null); };
  const retryTickets = () => { setTicketLoading(true); setTicketError(null); void loadTickets(); };
  const navLink = (name: Page, Icon: typeof Home) => <button className={`nav-link ${page === name ? 'active' : ''}`} key={name} onClick={() => makePage(name)}><Icon size={17} strokeWidth={1.8} /><span>{name}</span>{name === 'Tickets' && <span className="nav-count">{tickets.filter((t) => t.status !== 'Resolved').length}</span>}</button>;
  const displayIdentity = authUser?.login_identity ?? '';
  const initials = displayIdentity.split('@')[0].split(/[._\s-]+/).filter(Boolean).slice(0, 2).map((part) => part[0]?.toUpperCase()).join('') || 'U';
  const visibleNavigation = authUser?.role === 'admin' ? navigation : navigation.filter((item) => item.name !== 'Analytics');

  const renderDashboard = () => {
    const data = dashboard;
    const isAdmin = authUser?.role === 'admin';
    const dashboardSummary = isAdmin
      ? 'Review new requests and see which tickets are still being handled.'
      : 'A quick view of your open, in-progress, and resolved requests.';
    const recentTicketsHeading = isAdmin ? 'Latest tickets from all users' : 'Your recent tickets';
    const totalCount = tickets.length;
    const inProgressCount = tickets.filter((ticket) => ticket.status === 'In Progress').length;
    const resolvedCount = tickets.filter((ticket) => ticket.status === 'Resolved').length;
    const metricsReady = !ticketLoading && !ticketError;
    const retryDashboard = () => setDashboardReload((value) => value + 1);
    const viewTickets = (status: string) => {
      setStatusFilter(status);
      setPriorityFilter('All priorities');
      setTicketQuery('');
      makePage('Tickets');
    };
    return <>
      <div className="welcome-row"><div><div className="eyebrow">{isAdmin ? 'IT OPERATIONS' : 'MY SUPPORT'}</div><h1>{isAdmin ? 'Support tickets' : 'Your tickets'}</h1><p className="subheading">{dashboardSummary}</p></div><button className="button button-primary" onClick={() => setShowCreate(true)}><Plus size={16} /> Create ticket</button></div>
      {isAdmin && ticketError && <ApiError message={ticketError} title="Tickets could not be loaded" onRetry={retryTickets} />}
      {!isAdmin && dashboardError && <ApiError message={dashboardError} onRetry={retryDashboard} />}
      <section className={`kpi-grid ${isAdmin ? 'admin-ticket-kpis' : 'user-kpi-grid'}`} aria-label="Ticket summary">
        {isAdmin ? <>
          <Kpi title="Tickets" value={metricsReady ? String(totalCount) : '-'} icon={TicketIcon} tone="blue" detail="All submitted tickets" onClick={() => viewTickets('All statuses')} />
          <Kpi title="In progress" value={metricsReady ? String(inProgressCount) : '-'} icon={LoaderCircle} tone="amber" detail="Click to view these tickets" onClick={() => viewTickets('In Progress')} />
          <Kpi title="Resolved tickets" value={metricsReady ? String(resolvedCount) : '-'} icon={Check} tone="green" detail="Click to view these tickets" onClick={() => viewTickets('Resolved')} />
        </> : <>
          <Kpi title="Your open tickets" value={data ? String(data.open_tickets) : '-'} icon={TicketIcon} tone="blue" detail="Waiting for support" />
          <Kpi title="In progress" value={data ? String(data.in_progress_tickets) : '-'} icon={LoaderCircle} tone="amber" detail="Being worked on" />
          <Kpi title="Resolved tickets" value={data ? String(data.resolved_tickets) : '-'} icon={Check} tone="green" detail="Marked as resolved" />
        </>}
      </section>
      <section className={`lower-grid ${isAdmin ? 'admin-dashboard-recent' : 'user-dashboard-recent'}`}>
        <div className="card table-card">
          <div className="card-head"><div><h2>{isAdmin ? 'Recent user tickets' : 'Your recent tickets'}</h2><p>{recentTicketsHeading}</p></div><button className="text-link" onClick={() => makePage('Tickets')}>View all tickets <ChevronRight size={14} /></button></div>
          {isAdmin ? ticketLoading ? <LoadingState label="Loading user tickets..." /> : !ticketError ? <TicketTable tickets={tickets.slice(0, 8)} onSelect={openTicket} empty="No tickets have been submitted yet." showOwner /> : null : dashboardLoading ? <LoadingState label="Loading recent tickets..." /> : data ? <TicketTable tickets={data.recent_tickets} onSelect={openTicket} empty="No tickets have been created yet." /> : null}
        </div>
      </section>
    </>;
  };
  const renderTickets = () => <><PageIntro eyebrow="SUPPORT OPERATIONS" title="Tickets" text={authUser?.role === 'admin' ? 'Track, prioritize, and resolve IT requests across your organization.' : 'Track and follow your IT support requests.'} action={<button className="button button-primary" onClick={() => setShowCreate(true)}><Plus size={16} /> Create ticket</button>} />
    <div className="card tickets-card"><div className="ticket-controls"><label className="search-box ticket-search"><Search size={16}/><input aria-label="Search tickets" placeholder="Search tickets..." value={ticketQuery} onChange={(e) => {setTicketLoading(true);setTicketError(null);setTicketQuery(e.target.value);}} /><kbd>Command/Ctrl + K</kbd></label><select aria-label="Filter by status" value={statusFilter} onChange={(e) => {setTicketLoading(true);setTicketError(null);setStatusFilter(e.target.value);}}><option>All statuses</option><option>Open</option><option>In Progress</option><option>Resolved</option></select><select aria-label="Filter by priority" value={priorityFilter} onChange={(e) => {setTicketLoading(true);setTicketError(null);setPriorityFilter(e.target.value);}}><option>All priorities</option><option>High</option><option>Medium</option><option>Low</option></select><span className="result-count">{ticketLoading ? 'Loading...' : `${tickets.length} tickets`}</span></div>{ticketError ? <ApiError message={ticketError} onRetry={retryTickets} /> : ticketLoading ? <LoadingState label="Loading tickets..." /> : <TicketTable tickets={tickets} onSelect={openTicket} empty="No tickets match these filters. Try a different search." showOwner={authUser?.role === 'admin'} />}</div></>;

  const renderHelp = () => <><PageIntro eyebrow="AI POWERED SUPPORT" title="AI Help Center" text="Describe your issue and get guided troubleshooting in seconds." action={<button className="button button-outline" onClick={() => setShowCreate(true)}><FilePlus2 size={16} /> Create ticket</button>} /><div className="help-layout"><div className="card chat-card"><div className="chat-head"><div className="bot-avatar"><Bot size={20}/><span /></div><div><strong>IT Support Assistant</strong><small><i /> Groq via backend - server-side</small></div><button className="icon-button" aria-label="Chat options"><MoreHorizontal size={19}/></button></div><div className="chat-messages" aria-live="polite">{chat.map((item, i) => <div key={i} className={`message-row ${item.from}`}><div className="message-avatar">{item.from === 'bot' ? <Bot size={15}/> : 'AM'}</div><div className="message-content">{item.from === 'bot' && <small>{item.provider === 'groq' ? 'GROQ RESPONSE' : 'IT SUPPORT'}</small>}<div className="message-bubble">{item.from === 'bot' ? <ChatMarkdown>{item.text}</ChatMarkdown> : item.text}</div>{item.sources && item.sources.length > 0 && <div className="chat-sources"><small>RETRIEVED KNOWLEDGE-BASE ARTICLES</small>{item.sources.map((source) => <button key={source.title} onClick={() => {const index = articles.findIndex((article) => article.title === source.title);if (index >= 0) {setSelectedArticle(index);setPage('Knowledge Base');}}}><BookOpen size={12}/><span>{source.title}</span><ChevronRight size={12}/></button>)}</div>}{item.from === 'bot' && <span className="message-time">Just now</span>}</div></div>)}</div><div className="suggestion-area"><div className="suggestion-label">SUGGESTED ISSUES</div><div className="suggestions">{['Wi-Fi not connecting', 'VPN problem', 'Slow computer', 'Account access issue'].map((s) => <button key={s} disabled={chatSending} onClick={() => void sendMessage(s)}>{s}</button>)}</div></div>{chatError && <div className="api-error chat-error" role="alert"><CircleHelp size={16}/><span><strong>Groq response unavailable</strong>{chatError} Your ticket tools still work, or you can retry with another message.</span></div>}{workflowStartError && <div className="api-error chat-error" role="alert"><CircleHelp size={16}/><span><strong>Workflow could not start</strong>{workflowStartError}</span></div>}<form className="chat-input" onSubmit={(e) => { e.preventDefault(); void sendMessage(); }}><input aria-label="Describe your IT issue" placeholder="Describe your IT issue..." value={message} onChange={(e) => setMessage(e.target.value)} /><button type="submit" aria-label="Send message" disabled={!message.trim() || chatSending}>{chatSending ? <LoaderCircle size={17} className="spin"/> : <Send size={17}/>}</button></form><button className="button button-outline workflow-start-button" disabled={workflowStartLoading || (message.trim().length < 5 && lastChatIssue.length < 5)} onClick={() => void startWorkflow()}>{workflowStartLoading ? <LoaderCircle size={15} className="spin"/> : <Activity size={15}/>} Start safe troubleshooting workflow{lastChatIssue ? ' for last issue' : ''}</button><p className="mock-note"><CircleHelp size={13}/> Groq requests go through the backend. Workflow tool results are simulated; no device diagnostics or remediation are performed.</p></div><aside className="help-aside"><div className="card assist-card"><div className="assist-icon"><Sparkles size={19}/></div><h3>How can I help?</h3><p>Get step-by-step guidance for common IT issues, or create a ticket for our support team.</p><div className="assist-feature"><Check size={15}/> Safe troubleshooting steps</div><div className="assist-feature"><Check size={15}/> Relevant help articles</div><div className="assist-feature"><Check size={15}/> Escalation guidance</div><button className="button button-outline full-button" onClick={() => setShowCreate(true)}>Create a support ticket <ChevronRight size={15}/></button></div><div className="help-contact"><Headphones size={17}/><div><strong>Need a person?</strong><span>Our IT team is here to help.</span></div><button aria-label="Contact support" onClick={() => setShowCreate(true)}><ChevronRight size={16}/></button></div></aside></div></>;


  const renderKnowledge = () => selectedArticle !== null ? (() => { const article = articles[selectedArticle]; return <><button className="back-link" onClick={() => setSelectedArticle(null)}>Back to Knowledge Base</button><div className="article-detail"><span className="article-category">{article.category}</span><h1>{article.title}</h1><p>{article.intro}</p><div className="article-meta"><Clock3 size={15}/>{article.time}<span> - </span>Reviewed by IT Support</div><h2>Step-by-step guide</h2><ol>{article.steps.map((step, i) => <li key={step}><span>{i + 1}</span>{step}</li>)}</ol><div className="article-help">Still need help? <button onClick={() => { setSelectedArticle(null); setShowCreate(true); }}>Create a support ticket <ChevronRight size={14}/></button></div></div></>; })() : <><PageIntro eyebrow="SELF SERVICE" title="Knowledge base" text="Practical guides for the most common campus IT issues." /><div className="card knowledge-card"><div className="kb-controls"><label className="search-box"><Search size={16}/><input aria-label="Search help articles" placeholder="Search articles..." value={articleQuery} onChange={(e) => setArticleQuery(e.target.value)}/></label><select aria-label="Filter by category" value={articleFilter} onChange={(e) => setArticleFilter(e.target.value)}>{['All articles', 'Network', 'Access', 'Hardware', 'Account', 'Software'].map((c) => <option key={c}>{c}</option>)}</select></div><div className="article-grid">{filteredArticles.map((article) => <button className="article-card" key={article.title} onClick={() => setSelectedArticle(article.index)}><span className="article-icon"><BookOpen size={18}/></span><span className="article-category">{article.category}</span><strong>{article.title}</strong><span className="article-intro">{article.intro}</span><span className="article-footer">{article.time}<span>Read guide <ChevronRight size={14}/></span></span></button>)}</div>{filteredArticles.length === 0 && <div className="empty-state"><BookOpen size={23}/><strong>No articles found</strong><span>Try another search term or category.</span></div>}</div></>;

  const renderAnalytics = () => {
    const data = analytics;
    const categoryTotal = data?.category_distribution.reduce((total, item) => total + item.count, 0) ?? 0;
    const bucketSize = data ? Math.max(1, Math.ceil(data.daily_volume.length / 12)) : 1;
    const bars: { date: string; created: number; resolved: number }[] = [];
    if (data) {
      for (let index = 0; index < data.daily_volume.length; index += bucketSize) {
        const days = data.daily_volume.slice(index, index + bucketSize);
        bars.push({
          date: days[0].date,
          created: days.reduce((total, day) => total + day.created, 0),
          resolved: days.reduce((total, day) => total + day.resolved, 0),
        });
      }
    }
    const chartMax = Math.max(1, ...bars.flatMap((bar) => [bar.created, bar.resolved]));
    const retryAnalytics = () => setAnalyticsReload((value) => value + 1);
    const categoryColors = ['blue', 'violet', 'amber', 'green', 'slate'];
    return <>
      <PageIntro eyebrow="SERVICE PERFORMANCE" title="Analytics" text="Organization ticket trends calculated from persisted helpdesk records." action={<select className="select-button" aria-label="Analytics date range" value={analyticsDays} onChange={(event) => setAnalyticsDays(Number(event.target.value))}><option value={7}>Last 7 days</option><option value={30}>Last 30 days</option><option value={90}>Last 90 days</option></select>} />
      {analyticsError ? <ApiError message={analyticsError} title="Analytics could not be loaded" onRetry={retryAnalytics} /> : analyticsLoading ? <LoadingState label="Loading live analytics..." /> : data ? <>
        <div className="kpi-grid analytics-kpis">
          <Kpi title="Tickets created" value={String(data.total_tickets)} icon={TicketIcon} tone="blue" detail={`In the last ${data.days} days`} />
          <Kpi title="Avg. first response" value={data.average_first_response_minutes == null ? 'Not enough data' : `${data.average_first_response_minutes} min`} icon={Clock3} tone="amber" detail="First-response times are not recorded" />
          <Kpi title="Resolution rate" value={data.resolution_rate_percent == null ? 'Not enough data' : `${data.resolution_rate_percent}%`} icon={Check} tone="green" detail={`${data.resolved_tickets} of ${data.total_tickets} tickets resolved`} />
          <Kpi title="Tickets with AI workflow" value={String(data.tickets_with_workflow)} icon={Bot} tone="violet" detail="Linked persisted workflow runs" />
        </div>
        <div className="analytics-grid">
          <div className="card analytics-chart">
            <div className="card-head"><div><h2>Support volume</h2><p>Created and resolved tickets, grouped from actual timestamps</p></div></div>
            {data.total_tickets === 0 && bars.every((bar) => bar.created === 0 && bar.resolved === 0) ? <div className="analytics-empty"><TicketIcon size={22}/><strong>No ticket activity in this period</strong><span>Choose a longer date range or check back after tickets are created.</span></div> : <div className="bar-chart" role="img" aria-label={`Created and resolved ticket counts for the last ${data.days} days`}>
              {bars.map((bar, index) => <div key={`${bar.date}-${index}`} className="bar-group"><span title={`${bar.created} tickets created`} style={{height: `${bar.created / chartMax * 100}%`}}/><span title={`${bar.resolved} tickets resolved`} style={{height: `${bar.resolved / chartMax * 100}%`}}/><small>{new Date(`${bar.date}T00:00:00Z`).toLocaleDateString(undefined, { month: 'short', day: 'numeric', timeZone: 'UTC' })}</small></div>)}
            </div>}
            <div className="chart-legend"><span><i className="legend-blue"/> Created</span><span><i className="legend-green"/> Resolved</span></div>
          </div>
          <div className="card category-card"><div className="card-head"><div><h2>Tickets by category</h2><p>Share of tickets created during this period</p></div></div>
            {data.category_distribution.length === 0 ? <div className="analytics-empty compact"><strong>No categories to show yet</strong><span>Category totals will appear when tickets are created.</span></div> : data.category_distribution.map((item, index) => {
              const percent = categoryTotal ? Math.round(item.count / categoryTotal * 100) : 0;
              return <div className="category-row" key={item.category}><span>{item.category}</span><div className="category-track"><i className={`fill-${categoryColors[index % categoryColors.length]}`} style={{width: `${percent}%`}}/></div><strong>{percent}% <small>({item.count})</small></strong></div>;
            })}
          </div>
        </div>
      </> : null}
    </>;
  };

  const renderSettings = () => <><PageIntro eyebrow="PREFERENCES" title="Settings" text="Manage your profile and dashboard preferences."/><div className="settings-grid"><div className="card settings-card"><h2>Profile</h2><p>Account details for the signed-in workspace account.</p><div className="profile-setting"><span className="profile-avatar large">{initials}</span><div><strong>{displayIdentity}</strong><span>{authUser?.role === 'admin' ? 'Administrator' : 'User'}</span></div></div><div className="setting-field"><label>Login identity</label><input value={displayIdentity} readOnly/></div><div className="setting-field"><label>Role</label><input value={authUser?.role ?? ''} readOnly/></div></div><div className="card settings-card"><h2>Preferences</h2><p>Dashboard options for this session.</p><Preference label="Email notifications" detail="Receive updates for assigned tickets"/><Preference label="AI assistance" detail="Show AI suggestions in ticket workflows"/><Preference label="Weekly summary" detail="Display a weekly support performance recap"/></div></div></>;

  const content = page === 'Dashboard' ? renderDashboard() : page === 'Tickets' ? renderTickets() : page === 'AI Help Center' ? renderHelp() : page === 'Agentic Workflow Monitor' ? <WorkflowMonitor runs={workflowRuns} loading={workflowLoading} error={workflowError} selectedId={selectedWorkflowId} onSelect={setSelectedWorkflowId} onRefresh={() => void refreshWorkflows()} onConfirm={(fixed) => void confirmSelectedWorkflow(fixed)} confirming={workflowConfirming} onStart={() => setPage('AI Help Center')} /> : page === 'Knowledge Base' ? renderKnowledge() : page === 'Analytics' ? renderAnalytics() : renderSettings();

  if (authStatus === 'loading') return <main className="auth-loading" role="status" aria-live="polite"><LoaderCircle className="spin" size={22}/> Checking your session...</main>;
  if (authStatus === 'signed-out') return <LoginPage loading={authBusy} error={authError} onLogin={handleLogin}/>;

  return <div className="app-shell"><aside id="app-sidebar" className={`sidebar ${mobileMenu ? 'mobile-open' : ''}`} aria-hidden={!mobileMenu} inert={!mobileMenu}><div className="brand"><div className="brand-mark"><Command size={19}/><span/></div><div className="brand-copy"><strong>Helpdesk AI</strong><small>IT OPERATIONS</small></div><button className="mobile-close" aria-label="Close navigation" onClick={() => setMobileMenu(false)}><X size={18}/></button></div><nav className="nav-main" aria-label="Main navigation"><span className="nav-section">WORKSPACE</span>{visibleNavigation.map(({name, icon}) => navLink(name, icon))}<span className="nav-section tools-label">PREFERENCES</span>{navLink('Settings', Settings)}</nav><div className="sidebar-bottom"><div className="sidebar-help"><div className="help-top"><LifeBuoy size={16}/><span>Need a hand?</span></div><p>Visit our help center for guidance.</p><button onClick={() => makePage('AI Help Center')}>Get support <ChevronRight size={13}/></button></div><button className="sidebar-user" onClick={() => setProfileOpen(!profileOpen)}><span className="profile-avatar">{initials}</span><span className="user-copy"><strong>{displayIdentity}</strong><small>{authUser?.role === 'admin' ? 'Administrator' : 'User'}</small></span><MoreHorizontal size={18}/></button></div></aside>
    {mobileMenu && <button className="mobile-backdrop" aria-label="Close navigation" onClick={() => setMobileMenu(false)}/>}
    <main className="main-shell"><header className="topbar"><div className="topbar-left"><button id="sidebar-toggle" className="mobile-menu-button" aria-label={mobileMenu ? 'Close navigation' : 'Open navigation'} aria-expanded={mobileMenu} aria-controls="app-sidebar" onClick={() => setMobileMenu((open) => !open)}>{mobileMenu ? <X size={19}/> : <Menu size={19}/>}</button><div className="breadcrumbs"><span>Workspace</span><ChevronRight size={14}/><strong>{page}</strong></div></div><div className="topbar-actions"><div className="global-search-wrap"><label className="search-box global-search"><Search size={16}/><input id="global-search" aria-label="Search tickets and articles" placeholder="Search anything..." value={query} onChange={(e) => setQuery(e.target.value)}/><kbd>Command/Ctrl + K</kbd></label>{query && <div className="search-results">{globalResults.length ? globalResults.map((r, i) => <button key={i} onClick={() => {makePage(r.page); setQuery('');}}><Search size={14}/><span><strong>{r.label}</strong><small>{r.sub}</small></span><ChevronRight size={14}/></button>) : <div className="search-empty">No tickets or articles found.</div>}</div>}</div><div className="top-action-wrap"><button className="top-icon" aria-label="Notifications" onClick={() => setNotificationOpen(!notificationOpen)}><Bell size={18}/><i/></button>{notificationOpen && <div className="top-popover notification-popover"><strong>Notifications</strong><span className="notification-item">Notification data is not available yet.</span></div>}</div><div className="top-action-wrap"><button className="top-profile" onClick={() => setProfileOpen(!profileOpen)}><span className="profile-avatar">{initials}</span><span>{displayIdentity}</span><ChevronDown size={14}/></button>{profileOpen && <div className="top-popover profile-popover"><strong>{displayIdentity}</strong><small>{authUser?.role === 'admin' ? 'Administrator' : 'User'}</small><button onClick={() => {setProfileOpen(false);makePage('Settings');}}>Profile settings</button>{logoutError && <small className="logout-error" role="alert">{logoutError}</small>}<button className="logout-button" onClick={() => void handleLogout()} disabled={authBusy}>{authBusy ? 'Signing out…' : 'Sign out'}</button></div>}</div></div></header><div className="content-area">{content}<footer className="app-footer"><span>Helpdesk AI <b> - </b> Frontend demo</span><span>No live service status available.</span></footer></div></main>
    {showCreate && <div className="modal-backdrop" role="presentation" onMouseDown={(e) => {if (e.target === e.currentTarget && !ticketCreateLoading) setShowCreate(false);}}><form className="modal-card" role="dialog" aria-modal="true" aria-labelledby="create-ticket-title" tabIndex={-1} ref={createDialogRef} onSubmit={createTicket}><div className="modal-head"><div><span className="modal-icon"><FilePlus2 size={18}/></span><h2 id="create-ticket-title">Create a ticket</h2><p>Tell us what you need help with.</p></div><button type="button" className="icon-button" aria-label="Close dialog" onClick={() => setShowCreate(false)} disabled={ticketCreateLoading}><X size={18}/></button></div><label className="form-field">Issue title<input name="title" placeholder="e.g. Can't connect to campus Wi-Fi" required minLength={5} maxLength={90}/></label><div className="form-row"><label className="form-field">Category<select name="category"><option>Network</option><option>Account</option><option>Hardware</option><option>Software</option><option>Access</option><option>Other</option></select></label><label className="form-field">Priority<select name="priority"><option>Low</option><option>Medium</option><option>High</option></select></label></div><label className="form-field">Description<textarea name="description" placeholder="Include what happened and any steps you have tried..." required minLength={10} rows={4}/><small>At least 10 characters. Do not include passwords or sensitive information.</small></label>{ticketCreateError && <div className="api-error form-error" role="alert"><CircleHelp size={16}/><span><strong>Ticket was not created</strong>{ticketCreateError}</span></div>}<div className="modal-actions"><button type="button" className="button button-outline" onClick={() => setShowCreate(false)} disabled={ticketCreateLoading}>Cancel</button><button type="submit" className="button button-primary" disabled={ticketCreateLoading}>{ticketCreateLoading ? <LoaderCircle size={15} className="spin"/> : <Plus size={15}/>} {ticketCreateLoading ? 'Submitting...' : 'Submit ticket'}</button></div></form></div>}
    {selectedTicket && <div className="modal-backdrop" role="presentation" onMouseDown={(e) => {if (e.target === e.currentTarget && !ticketDetailLoading) setSelectedTicket(null);}}><div className="modal-card detail-modal" role="dialog" aria-modal="true" aria-labelledby="ticket-detail-title" tabIndex={-1} ref={ticketDetailDialogRef}><div className="modal-head"><div><span className="ticket-id">{selectedTicket.id}</span><h2 id="ticket-detail-title">{selectedTicket.title}</h2><p>Created by {selectedTicket.owner} - {selectedTicket.updated}</p></div><button className="icon-button" aria-label="Close ticket details" onClick={() => setSelectedTicket(null)}><X size={18}/></button></div>{ticketDetailLoading ? <LoadingState label="Loading ticket details..." /> : ticketDetailError ? <ApiError message={ticketDetailError} title="Ticket details could not be loaded" onRetry={() => void openTicket(selectedTicket)} /> : <><div className="detail-badges"><StatusBadge value={selectedTicket.status}/><PriorityBadge value={selectedTicket.priority}/><span className="category-chip">{selectedTicket.category}</span></div><div className="detail-section"><h3>Description</h3><p>{selectedTicket.description}</p></div><div className="detail-section"><h3>Activity</h3><div className="detail-activity"><span className="activity-icon"><TicketIcon size={14}/></span><div><strong>Ticket created</strong><small>{selectedTicket.updated} - by {selectedTicket.owner}</small></div></div></div>{selectedTicket.resolution && <div className="detail-section ticket-resolution"><h3>{selectedTicket.status === 'Resolved' ? 'Resolution provided' : 'Previous resolution'}</h3><p>{selectedTicket.resolution}</p></div>}{authUser?.role === 'admin' && <div className="ticket-status-actions" aria-label="Admin ticket status actions">{ticketStatusError && <div className="api-error form-error" role="alert"><CircleHelp size={16}/><span><strong>Status was not updated</strong>{ticketStatusError}</span></div>}{selectedTicket.status !== 'Resolved' && <label className="form-field" htmlFor="ticket-resolution">Resolution / fix applied<textarea id="ticket-resolution" value={ticketResolution} onChange={(event) => {setTicketResolution(event.target.value);setTicketStatusError(null);}} minLength={10} maxLength={2000} rows={3} placeholder="Describe what was done and how the requester can verify it."/><small>Required before resolving; 10–2,000 characters.</small></label>}<div className="modal-actions">{selectedTicket.status === 'Open' && <button className="button button-outline" disabled={ticketStatusSaving} onClick={() => void changeTicketStatus('In Progress')}>{ticketStatusSaving ? 'Saving...' : 'Mark in progress'}</button>}{selectedTicket.status !== 'Resolved' ? <button className="button button-primary" disabled={ticketStatusSaving || ticketResolution.trim().length < 10} onClick={() => void changeTicketStatus('Resolved', ticketResolution)}>{ticketStatusSaving ? 'Saving...' : 'Resolve with solution'}</button> : <button className="button button-outline" disabled={ticketStatusSaving} onClick={() => void changeTicketStatus('Open')}>{ticketStatusSaving ? 'Saving...' : 'Reopen ticket'}</button>}</div></div>}<button className="button button-primary full-button" onClick={() => {setSelectedTicket(null);makePage('Agentic Workflow Monitor');}}>View workflow <ChevronRight size={15}/></button></>}</div></div>}
  </div>;
}

function Kpi({title,value,change,direction,icon: Icon,tone,detail,onClick}: {title:string;value:string;change?:string;direction?:'up'|'down';icon:typeof Home;tone:string;detail:string;onClick?:()=>void}) {
  const content = <><div className="kpi-top"><span>{title}</span><span className={`kpi-icon ${tone}`}><Icon size={17}/></span></div><div className="kpi-bottom"><strong className={value.length > 10 ? 'kpi-value-long' : ''}>{value}</strong>{change && direction && <span className={`kpi-change ${direction}`}>{direction === 'up' ? <ArrowUpRight size={13}/> : <ArrowDownRight size={13}/>} {change}</span>}</div><div className="kpi-detail">{detail}</div></>;
  return onClick
    ? <button type="button" className="card kpi-card kpi-card-action" onClick={onClick} aria-label={`${title}: ${value}. ${detail}. View tickets.`}>{content}</button>
    : <div className="card kpi-card">{content}</div>;
}
function workflowStatusText(status: string) {
  if (status === 'awaiting_user') return 'Waiting for your update';
  if (status === 'needs_escalation') return 'IT support recommended';
  if (status === 'user_confirmed_resolved') return 'You marked this fixed';
  return status.replaceAll('_', ' ');
}

function WorkflowMonitor({runs,loading,error,selectedId,onSelect,onRefresh,onConfirm,confirming,onStart}: {runs:WorkflowRun[];loading:boolean;error:string|null;selectedId:string|null;onSelect:(id:string)=>void;onRefresh:()=>void;onConfirm:(fixed:boolean)=>void;confirming:boolean;onStart:()=>void}) {
  const run = runs.find((item) => item.id === selectedId) ?? runs[0];
  const viewState = workflowViewState(loading, error, runs.length);
  const statusText = run ? workflowStatusText(run.status) : '';
  const resultText = run && typeof run.tool_output.result === 'string' ? run.tool_output.result : 'The sample check finished. No device or network was contacted.';
  const resultTone = run?.verification.passed === true ? 'pass' : run?.verification.passed === false ? 'fail' : 'inconclusive';
  return <>
    <PageIntro eyebrow="TROUBLESHOOTING" title="Workflow monitor" text="See the issue, simple steps to try, and what to do next." action={<button className="button button-outline" onClick={onRefresh}><Clock3 size={15}/> Refresh</button>} />
    {error && <div className="api-error" role="alert"><CircleHelp size={16}/><span><strong>Workflow data unavailable</strong>{error}</span><button className="button button-outline" onClick={onRefresh}>Retry</button></div>}
    {viewState === 'loading' ? <div className="card api-loading"><LoaderCircle className="spin" size={18}/> Loading workflows...</div> : viewState === 'error' ? null : viewState === 'empty' ? <div className="card workflow-empty"><Activity size={25}/><h2>No troubleshooting yet</h2><p>Start from an issue in AI Help Center to get suggested steps.</p><button className="button button-primary" onClick={onStart}>Go to AI Help Center</button></div> : run ? <>
      <div className="workflow-layout">
        <div className="card workflow-card workflow-live-card">
          <div className="workflow-top">
            <div className="workflow-ticket"><span className="workflow-avatar"><Network size={17}/></span><div><small>YOUR ISSUE</small><strong>{run.diagnosis.summary}</strong><span>{run.diagnosis.category} · {new Date(run.created_at).toLocaleString()}</span></div></div>
            <span className={`workflow-state ${run.status === 'awaiting_user' ? 'waiting' : run.status === 'needs_escalation' ? 'help' : 'done'}`}>{statusText}</span>
          </div>

          <section className="workflow-issue"><h2>What you reported</h2><p>{run.issue}</p><div className="diagnosis-grid"><span>Category <b>{run.diagnosis.category}</b></span><span>Suggested priority <b>{run.diagnosis.suggested_priority}</b></span></div><small className="ai-suggestion-tag"><Bot size={12}/> AI suggestions — not verified</small></section>

          <section className="workflow-steps">
            <h2>What might be causing it</h2>
            <ul>{run.diagnosis.likely_causes.map((cause) => <li key={cause}>{cause}</li>)}</ul>
            <h2>Steps you can try</h2>
            <ol>{run.diagnosis.troubleshooting_steps.map((step) => <li key={step}>{step}</li>)}</ol>
          </section>

          <section className="simulated-tool-panel workflow-demo-result">
            <div className="workflow-section-title"><h2>Demo check</h2><span><LockKeyhole size={13}/> SIMULATED</span></div>
            <p className="workflow-tool-name">{run.tool_name.replaceAll('_', ' ')}</p>
            <p>{resultText}</p>
            <div className={`verification-result ${resultTone}`}>
              {run.verification.passed === true ? 'Sample check matched' : run.verification.passed === false ? 'Sample check did not match' : 'No clear sample result'}
              <small>This is only a demo. It did not check or change your device.</small>
            </div>
            <details className="workflow-more"><summary>How the demo check was evaluated</summary><p>{run.verification.criterion}</p><p>{run.verification.reason}</p></details>
          </section>

          {run.sources.length > 0 && <section className="workflow-sources"><h2><BookOpen size={15}/> Helpful articles</h2>{run.sources.map((source) => <span key={source.title}>{source.title} · {source.category}</span>)}</section>}

          <section className="workflow-next">
            <h2>Suggested fix</h2><p>{run.proposed_resolution}</p><small>Guidance only — no fix was applied automatically.</small>
            <h3>What to do next</h3><p>{run.next_action}</p>
            {run.ticket_id && <p className="workflow-linked-ticket">Support ticket: {run.ticket_id}</p>}
            {run.status === 'awaiting_user' && <div className="workflow-confirm-actions"><strong>After trying the steps, is the issue fixed?</strong><button className="button button-primary" disabled={confirming} onClick={() => onConfirm(true)}>{confirming ? 'Saving...' : 'Yes, it is fixed'}</button><button className="button button-outline" disabled={confirming} onClick={() => onConfirm(false)}>No, I need IT help</button></div>}
          </section>

          <details className="workflow-audit workflow-more"><summary>Technical activity ({run.events.length})</summary><p>Reference: {run.id}</p>{run.events.map((event,index) => <div className="workflow-audit-event" key={`${event.stage}-${index}`}><span className={`audit-dot ${event.status}`}/><div><strong>{event.stage.replaceAll('_',' ')}</strong><p>{event.detail}</p><small>{event.created_at.replace('T',' ').slice(0,19)}</small></div></div>)}</details>
        </div>

        <aside className="card workflow-summary"><h2>At a glance</h2><div className="summary-stat"><span>Status</span><strong>{statusText}</strong></div>{run.ticket_id && <div className="workflow-linked-ticket">Support ticket: {run.ticket_id}</div>}<div className="workflow-safety-note"><LockKeyhole size={15}/><span>Demo only. Nothing on your device has been checked or changed.</span></div></aside>
      </div>

      {runs.length > 1 && <section className="card workflow-history"><div className="card-head"><div><h2>Earlier troubleshooting</h2><p>Choose an issue to view its steps.</p></div></div>{runs.filter((item) => item.id !== run.id).map((item) => <button className="history-row workflow-run-row" key={item.id} onClick={() => onSelect(item.id)}><span className="history-icon amber"><Activity size={15}/></span><span><strong>{item.diagnosis.summary}</strong><small>{item.diagnosis.category}{item.ticket_id ? ` · Ticket ${item.ticket_id}` : ''}</small></span><span className="history-result">{workflowStatusText(item.status)}</span><small>{new Date(item.created_at).toLocaleDateString()}</small></button>)}</section>}
    </> : null}
  </>;
}

function PageIntro({eyebrow,title,text,action}: {eyebrow:string;title:string;text:string;action?:React.ReactNode}) { return <div className="page-intro"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{text}</p></div>{action}</div>; }
function LoadingState({label}: {label:string}) { return <div className="api-loading" role="status"><LoaderCircle size={17} className="spin"/><span>{label}</span></div>; }
function ApiError({message,onRetry,title='Helpdesk API unavailable'}: {message:string;onRetry:()=>void;title?:string}) { return <div className="api-error" role="alert"><CircleHelp size={17}/><span><strong>{title}</strong>{message}</span><button className="button button-outline" onClick={onRetry}>Retry</button></div>; }
function TicketTable({tickets,onSelect,empty='No tickets yet.',showOwner=false}: {tickets:Ticket[];onSelect:(ticket:Ticket)=>void;empty?:string;showOwner?:boolean}) { return <div className="table-scroll"><table className="ticket-table"><thead><tr><th>Ticket</th>{showOwner && <th>Requester</th>}<th>Category</th><th>Priority</th><th>Status</th><th>Last updated</th><th/></tr></thead><tbody>{tickets.map((ticket) => <tr key={ticket.id} onClick={() => onSelect(ticket)} tabIndex={0} aria-label={`Open ticket ${ticket.id}: ${ticket.title}`} onKeyDown={(e) => {if(e.target !== e.currentTarget || e.repeat) return; if(e.key === 'Enter' || e.key === ' ' || e.code === 'Space') {e.preventDefault(); onSelect(ticket);}}}><td><span className="ticket-main"><span className="ticket-id">{ticket.id}</span><strong>{ticket.title}</strong></span></td>{showOwner && <td>{ticket.owner || 'Unknown requester'}</td>}<td><span className="category-chip">{ticket.category}</span></td><td><PriorityBadge value={ticket.priority}/></td><td><StatusBadge value={ticket.status}/></td><td className="updated-cell">{ticket.updated}</td><td><button className="row-more" aria-label={`View ${ticket.id}`} onClick={(e) => {e.stopPropagation();onSelect(ticket);}}><ChevronRight size={15}/></button></td></tr>)}</tbody></table>{tickets.length === 0 && <div className="empty-state"><Filter size={22}/><strong>No matching tickets</strong><span>{empty}</span></div>}</div>; }
function Preference({label,detail}: {label:string;detail:string}) {const [enabled,setEnabled]=useState(true);return <div className="preference"><div><strong>{label}</strong><span>{detail}</span></div><button aria-label={`${label} ${enabled?'on':'off'}`} className={`toggle ${enabled?'on':''}`} onClick={()=>setEnabled(!enabled)}><i/></button></div>;}

export default App;
