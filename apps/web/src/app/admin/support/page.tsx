'use client';

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  LifeBuoy,
  RefreshCw,
  Search,
  Filter,
  CheckCircle2,
  AlertCircle,
  Clock,
  MessageSquare,
  Paperclip,
  Send,
  X,
  ChevronLeft,
  ChevronRight,
  ShieldCheck,
  User,
  Building,
  MapPin,
  ExternalLink,
  ChevronDown,
} from 'lucide-react';
import { PageHeader } from '@/components/admin/PageHeader';
import { api, ApiClientError } from '@/lib/api-client';
import {
  AdminSupportTicketItem,
  AdminSupportTicketStats,
  AdminSupportTicketDetailResponse,
  SupportReplyItem,
} from '@/types/api';

const SUPPORT_CATEGORIES = [
  'Project Submission',
  'GitHub / Repository Issue',
  'Team & Member Issue',
  'AI Evaluation / Judging',
  'Results & Leaderboard',
  'Account & Login',
  'Event Related',
  'Venue / Seating Query',
  'Technical Issue',
  'Other',
];

const STATUS_CONFIG: Record<
  string,
  { label: string; badgeClass: string; dotClass: string }
> = {
  open: {
    label: 'Open',
    badgeClass: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    dotClass: 'bg-amber-400',
  },
  in_progress: {
    label: 'In Progress',
    badgeClass: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    dotClass: 'bg-blue-400',
  },
  waiting_response: {
    label: 'Waiting on Participant',
    badgeClass: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
    dotClass: 'bg-purple-400',
  },
  resolved: {
    label: 'Resolved',
    badgeClass: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    dotClass: 'bg-emerald-400',
  },
  closed: {
    label: 'Closed',
    badgeClass: 'bg-gray-500/10 text-gray-400 border-gray-500/20',
    dotClass: 'bg-gray-400',
  },
};

export default function AdminSupportPage() {
  const [tickets, setTickets] = useState<AdminSupportTicketItem[]>([]);
  const [stats, setStats] = useState<AdminSupportTicketStats>({
    total: 0,
    open: 0,
    in_progress: 0,
    waiting_response: 0,
    resolved: 0,
    closed: 0,
  });
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [limit] = useState(15);

  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [categoryFilter, setCategoryFilter] = useState('all');

  // Selected Ticket & Detail Modal
  const [selectedTicketId, setSelectedTicketId] = useState<string | null>(null);
  const [ticketDetail, setTicketDetail] = useState<AdminSupportTicketDetailResponse | null>(null);
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  // Reply State
  const [replyMessage, setReplyMessage] = useState('');
  const [isSendingReply, setIsSendingReply] = useState(false);
  const [isUpdatingStatus, setIsUpdatingStatus] = useState(false);

  const abortControllerRef = useRef<AbortController | null>(null);

  // Load tickets list
  const loadTickets = useCallback(async () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setIsLoading(true);
    setError(null);

    try {
      const res = await api.getAdminSupportTickets(
        {
          status: statusFilter,
          category: categoryFilter,
          search: debouncedSearch,
          page,
          limit,
        },
        { signal: controller.signal }
      );

      if (!controller.signal.aborted) {
        setTickets(res.items || []);
        setTotal(res.total || 0);
        setTotalPages(res.total_pages || 1);
        if (res.stats) {
          setStats(res.stats);
        }
      }
    } catch (err: unknown) {
      if (controller.signal.aborted) return;
      if (err instanceof ApiClientError) {
        if (err.code === 'REQUEST_ABORTED') return;
        setError(err.message);
      } else {
        setError('Failed to load support requests. Check your connection.');
      }
    } finally {
      if (!controller.signal.aborted) {
        setIsLoading(false);
      }
    }
  }, [page, limit, debouncedSearch, statusFilter, categoryFilter]);

  useEffect(() => {
    loadTickets();
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [loadTickets]);

  // Load Ticket Detail
  const openTicketDetail = async (ticketId: string) => {
    setSelectedTicketId(ticketId);
    setIsDetailLoading(true);
    setDetailError(null);
    setReplyMessage('');

    try {
      const detail = await api.getAdminSupportTicketDetail(ticketId);
      setTicketDetail(detail);
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setDetailError(err.message);
      } else {
        setDetailError('Failed to load ticket details.');
      }
    } finally {
      setIsDetailLoading(false);
    }
  };

  const closeTicketDetail = () => {
    setSelectedTicketId(null);
    setTicketDetail(null);
    setDetailError(null);
    setReplyMessage('');
  };

  // Submit Reply
  const handleSendReply = async (newStatus?: string) => {
    if (!selectedTicketId || !replyMessage.trim() || isSendingReply) return;

    setIsSendingReply(true);
    setDetailError(null);

    try {
      const newReply = await api.replyAdminSupportTicket(selectedTicketId, {
        message: replyMessage.trim(),
        status: newStatus,
      });

      // Update state
      if (ticketDetail) {
        const updatedTicket = {
          ...ticketDetail.ticket,
          status: newStatus || 'waiting_response',
          updated_at: new Date().toISOString(),
          replies_count: ticketDetail.ticket.replies_count + 1,
        };
        setTicketDetail({
          ticket: updatedTicket,
          replies: [...ticketDetail.replies, newReply],
        });
      }

      setReplyMessage('');
      setSuccessMessage('Reply sent successfully.');
      setTimeout(() => setSuccessMessage(null), 3500);

      // Refresh list in background
      loadTickets();
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setDetailError(err.message);
      } else {
        setDetailError('Failed to submit reply.');
      }
    } finally {
      setIsSendingReply(false);
    }
  };

  // Update Status
  const handleStatusChange = async (targetStatus: string) => {
    if (!selectedTicketId || isUpdatingStatus) return;

    setIsUpdatingStatus(true);
    setDetailError(null);

    try {
      const res = await api.updateAdminSupportTicketStatus(selectedTicketId, targetStatus);
      if (ticketDetail) {
        setTicketDetail({
          ...ticketDetail,
          ticket: {
            ...ticketDetail.ticket,
            status: res.status,
            updated_at: new Date().toISOString(),
          },
        });
      }

      setSuccessMessage(`Ticket status updated to ${STATUS_CONFIG[targetStatus]?.label || targetStatus}.`);
      setTimeout(() => setSuccessMessage(null), 3000);

      // Refresh list
      loadTickets();
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setDetailError(err.message);
      } else {
        setDetailError('Failed to update ticket status.');
      }
    } finally {
      setIsUpdatingStatus(false);
    }
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setDebouncedSearch(searchQuery);
    setPage(1);
  };

  const handleClearFilters = () => {
    setSearchQuery('');
    setDebouncedSearch('');
    setStatusFilter('all');
    setCategoryFilter('all');
    setPage(1);
  };

  const formatDate = (iso: string) => {
    try {
      const d = new Date(iso);
      return d.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return iso;
    }
  };

  const isFiltered = debouncedSearch || statusFilter !== 'all' || categoryFilter !== 'all';

  return (
    <div className="space-y-6">
      {/* Header */}
      <PageHeader
        title="Support Center"
        description="Monitor, triage, and resolve technical and logistical requests submitted by hackathon participants."
      >
        <button
          type="button"
          onClick={() => loadTickets()}
          disabled={isLoading}
          className="flex items-center gap-2 px-3.5 py-2 text-xs font-medium text-text-primary bg-surface-elevated hover:bg-surface-hover border border-surface-border rounded-lg transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          <span>Refresh</span>
        </button>
      </PageHeader>

      {/* Global Alerts */}
      {successMessage && (
        <div className="p-3.5 bg-emerald-500/10 border border-emerald-500/20 rounded-lg text-xs text-emerald-400 flex items-center gap-2 animate-fade-in">
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          <span>{successMessage}</span>
        </div>
      )}
      {error && (
        <div className="p-3.5 bg-rose-500/10 border border-rose-500/20 rounded-lg text-xs text-rose-400 flex items-center justify-between">
          <span>{error}</span>
          <button
            type="button"
            onClick={() => loadTickets()}
            className="underline font-semibold hover:text-white ml-2"
          >
            Retry
          </button>
        </div>
      )}

      {/* Metric Cards Row */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        <button
          type="button"
          onClick={() => {
            setStatusFilter('all');
            setPage(1);
          }}
          className={`p-4 rounded-xl border text-left transition-all ${
            statusFilter === 'all'
              ? 'bg-surface-elevated border-primary/50 shadow-sm shadow-primary/10'
              : 'bg-surface border-surface-border hover:border-surface-hover'
          }`}
        >
          <div className="flex items-center justify-between text-text-muted mb-1">
            <span className="text-xs font-medium">Total Requests</span>
            <LifeBuoy className="w-4 h-4 text-primary" />
          </div>
          <div className="text-2xl font-bold text-text-primary">{stats.total}</div>
          <div className="text-[11px] text-text-muted mt-0.5">Across all hackathons</div>
        </button>

        <button
          type="button"
          onClick={() => {
            setStatusFilter('open');
            setPage(1);
          }}
          className={`p-4 rounded-xl border text-left transition-all ${
            statusFilter === 'open'
              ? 'bg-amber-500/10 border-amber-500/40 shadow-sm shadow-amber-500/10'
              : 'bg-surface border-surface-border hover:border-surface-hover'
          }`}
        >
          <div className="flex items-center justify-between text-text-muted mb-1">
            <span className="text-xs font-medium text-amber-400">Open</span>
            <AlertCircle className="w-4 h-4 text-amber-400" />
          </div>
          <div className="text-2xl font-bold text-amber-400">{stats.open}</div>
          <div className="text-[11px] text-text-muted mt-0.5">Awaiting initial triage</div>
        </button>

        <button
          type="button"
          onClick={() => {
            setStatusFilter('in_progress');
            setPage(1);
          }}
          className={`p-4 rounded-xl border text-left transition-all ${
            statusFilter === 'in_progress'
              ? 'bg-blue-500/10 border-blue-500/40 shadow-sm shadow-blue-500/10'
              : 'bg-surface border-surface-border hover:border-surface-hover'
          }`}
        >
          <div className="flex items-center justify-between text-text-muted mb-1">
            <span className="text-xs font-medium text-blue-400">In Progress</span>
            <Clock className="w-4 h-4 text-blue-400" />
          </div>
          <div className="text-2xl font-bold text-blue-400">{stats.in_progress}</div>
          <div className="text-[11px] text-text-muted mt-0.5">Currently being handled</div>
        </button>

        <button
          type="button"
          onClick={() => {
            setStatusFilter('waiting_response');
            setPage(1);
          }}
          className={`p-4 rounded-xl border text-left transition-all ${
            statusFilter === 'waiting_response'
              ? 'bg-purple-500/10 border-purple-500/40 shadow-sm shadow-purple-500/10'
              : 'bg-surface border-surface-border hover:border-surface-hover'
          }`}
        >
          <div className="flex items-center justify-between text-text-muted mb-1">
            <span className="text-xs font-medium text-purple-400">Waiting Response</span>
            <MessageSquare className="w-4 h-4 text-purple-400" />
          </div>
          <div className="text-2xl font-bold text-purple-400">{stats.waiting_response}</div>
          <div className="text-[11px] text-text-muted mt-0.5">Staff replied to user</div>
        </button>

        <button
          type="button"
          onClick={() => {
            setStatusFilter('resolved');
            setPage(1);
          }}
          className={`p-4 rounded-xl border text-left transition-all ${
            statusFilter === 'resolved'
              ? 'bg-emerald-500/10 border-emerald-500/40 shadow-sm shadow-emerald-500/10'
              : 'bg-surface border-surface-border hover:border-surface-hover'
          }`}
        >
          <div className="flex items-center justify-between text-text-muted mb-1">
            <span className="text-xs font-medium text-emerald-400">Resolved</span>
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-bold text-emerald-400">{stats.resolved}</div>
          <div className="text-[11px] text-text-muted mt-0.5">Satisfactorily closed</div>
        </button>
      </div>

      {/* Search & Filter Toolbar */}
      <div className="p-4 bg-surface border border-surface-border rounded-xl flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 shadow-sm">
        <div className="flex flex-1 flex-col sm:flex-row items-stretch sm:items-center gap-3">
          {/* Search Box */}
          <form onSubmit={handleSearchSubmit} className="relative flex-1 sm:max-w-xs">
            <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by ticket #, subject, team, email..."
              className="w-full pl-9 pr-8 py-2 bg-surface-elevated border border-surface-border rounded-lg text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:border-primary transition-colors"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => {
                  setSearchQuery('');
                  setDebouncedSearch('');
                  setPage(1);
                }}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary p-0.5"
              >
                <X className="w-3 h-3" />
              </button>
            )}
          </form>

          {/* Status Filter */}
          <div className="relative sm:w-44">
            <select
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setPage(1);
              }}
              className="w-full appearance-none px-3 py-2 bg-surface-elevated border border-surface-border rounded-lg text-xs text-text-primary focus:outline-none focus:border-primary transition-colors cursor-pointer"
            >
              <option value="all">All Statuses</option>
              <option value="open">Open</option>
              <option value="in_progress">In Progress</option>
              <option value="waiting_response">Waiting Response</option>
              <option value="resolved">Resolved</option>
              <option value="closed">Closed</option>
            </select>
            <ChevronDown className="w-3.5 h-3.5 text-text-muted absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
          </div>

          {/* Category Filter */}
          <div className="relative sm:w-48">
            <select
              value={categoryFilter}
              onChange={(e) => {
                setCategoryFilter(e.target.value);
                setPage(1);
              }}
              className="w-full appearance-none px-3 py-2 bg-surface-elevated border border-surface-border rounded-lg text-xs text-text-primary focus:outline-none focus:border-primary transition-colors cursor-pointer"
            >
              <option value="all">All Categories</option>
              {SUPPORT_CATEGORIES.map((cat) => (
                <option key={cat} value={cat}>
                  {cat}
                </option>
              ))}
            </select>
            <ChevronDown className="w-3.5 h-3.5 text-text-muted absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
          </div>
        </div>

        {isFiltered && (
          <button
            type="button"
            onClick={handleClearFilters}
            className="text-xs text-text-muted hover:text-text-primary transition-colors flex items-center gap-1.5 self-start md:self-auto px-2 py-1"
          >
            <X className="w-3.5 h-3.5" />
            <span>Reset filters</span>
          </button>
        )}
      </div>

      {/* Tickets Table / List */}
      <div className="bg-surface border border-surface-border rounded-xl overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-text-secondary">
            <thead className="bg-surface-elevated/70 text-text-muted border-b border-surface-border font-medium text-[11px] uppercase tracking-wider">
              <tr>
                <th className="px-4 py-3.5">Ticket # & Subject</th>
                <th className="px-4 py-3.5">Participant & Team</th>
                <th className="px-4 py-3.5">Seating / Location</th>
                <th className="px-4 py-3.5">Category</th>
                <th className="px-4 py-3.5">Status</th>
                <th className="px-4 py-3.5">Replies</th>
                <th className="px-4 py-3.5">Submitted</th>
                <th className="px-4 py-3.5 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-border">
              {isLoading ? (
                <tr>
                  <td colSpan={8} className="py-12 text-center text-text-muted">
                    <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-primary" />
                    <span>Loading participant support requests...</span>
                  </td>
                </tr>
              ) : tickets.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-16 text-center text-text-muted">
                    <div className="max-w-sm mx-auto space-y-2">
                      <LifeBuoy className="w-10 h-10 mx-auto text-text-muted/40" />
                      <p className="text-sm font-semibold text-text-primary">
                        {isFiltered ? 'No matching tickets found' : 'No support requests yet'}
                      </p>
                      <p className="text-xs text-text-muted">
                        {isFiltered
                          ? 'Try adjusting your search criteria or clearing filters.'
                          : 'Participant support inquiries submitted from their portal will appear here in real time.'}
                      </p>
                      {isFiltered && (
                        <button
                          type="button"
                          onClick={handleClearFilters}
                          className="mt-3 px-3 py-1.5 bg-surface-elevated hover:bg-surface-hover border border-surface-border rounded-lg text-xs font-medium text-text-primary"
                        >
                          Clear Filters
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ) : (
                tickets.map((t) => {
                  const statusConf = STATUS_CONFIG[t.status] || {
                    label: t.status,
                    badgeClass: 'bg-gray-500/10 text-gray-400 border-gray-500/20',
                    dotClass: 'bg-gray-400',
                  };

                  return (
                    <tr
                      key={t.id}
                      onClick={() => openTicketDetail(t.id)}
                      className="hover:bg-surface-hover/60 transition-colors cursor-pointer group"
                    >
                      {/* Ticket # & Subject */}
                      <td className="px-4 py-3.5">
                        <div className="flex flex-col">
                          <span className="font-mono text-[11px] font-semibold text-primary group-hover:underline">
                            {t.ticket_number}
                          </span>
                          <span className="font-medium text-text-primary text-xs line-clamp-1 mt-0.5">
                            {t.subject}
                          </span>
                          {t.hackathon_title && (
                            <span className="text-[11px] text-text-muted line-clamp-1 mt-0.5">
                              {t.hackathon_title}
                            </span>
                          )}
                        </div>
                      </td>

                      {/* Participant & Team */}
                      <td className="px-4 py-3.5">
                        <div className="flex flex-col">
                          <span className="text-text-primary font-medium">
                            {t.participant_name || t.participant_email?.split('@')[0] || 'Unknown User'}
                          </span>
                          <span className="text-[11px] text-text-muted font-mono">
                            {t.participant_email || '—'}
                          </span>
                          <span className="text-[11px] text-text-secondary mt-0.5 flex items-center gap-1">
                            <Building className="w-3 h-3 text-text-muted" />
                            Team: {t.team_name}
                          </span>
                        </div>
                      </td>

                      {/* Seating / Location */}
                      <td className="px-4 py-3.5">
                        {t.category === 'Venue / Seating Query' ? (
                          <div className="text-text-primary font-medium text-xs flex items-center gap-1">
                            <MapPin className="w-3 h-3 text-amber-400 shrink-0" />
                            <span>Team #{t.team_number || '—'}</span>
                          </div>
                        ) : t.block_number || t.lab_number ? (
                          <div className="text-text-primary text-xs space-y-0.5">
                            <div className="font-medium text-primary flex items-center gap-1">
                              <MapPin className="w-3 h-3 text-primary shrink-0" />
                              <span>{t.block_number || '—'}</span>
                            </div>
                            <div className="text-[11px] text-text-muted">
                              Lab: {t.lab_number || '—'}
                            </div>
                          </div>
                        ) : (
                          <span className="text-text-muted">—</span>
                        )}
                      </td>

                      {/* Category */}
                      <td className="px-4 py-3.5">
                        <span className="inline-block px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-surface-elevated border border-surface-border text-text-secondary">
                          {t.category}
                        </span>
                      </td>

                      {/* Status */}
                      <td className="px-4 py-3.5">
                        <span
                          className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium border ${statusConf.badgeClass}`}
                        >
                          <span className={`w-1.5 h-1.5 rounded-full ${statusConf.dotClass}`} />
                          {statusConf.label}
                        </span>
                      </td>

                      {/* Replies & Attachment */}
                      <td className="px-4 py-3.5 text-text-muted">
                        <div className="flex items-center gap-2">
                          <span className="flex items-center gap-1 text-[11px]">
                            <MessageSquare className="w-3 h-3" />
                            {t.replies_count}
                          </span>
                          {t.attachment_url && (
                            <span title="Diagnostic Attachment Included" className="text-primary">
                              <Paperclip className="w-3.5 h-3.5" />
                            </span>
                          )}
                        </div>
                      </td>

                      {/* Submitted Date */}
                      <td className="px-4 py-3.5 text-text-muted text-[11px] whitespace-nowrap">
                        {formatDate(t.created_at)}
                      </td>

                      {/* Action */}
                      <td className="px-4 py-3.5 text-right">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            openTicketDetail(t.id);
                          }}
                          className="px-3 py-1 bg-surface-elevated hover:bg-surface-hover border border-surface-border text-text-primary font-medium rounded-lg text-xs transition-colors"
                        >
                          View & Reply
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Toolbar */}
        {!isLoading && total > 0 && (
          <div className="p-4 border-t border-surface-border flex items-center justify-between text-xs text-text-muted bg-surface/50">
            <div>
              Showing <span className="font-medium text-text-primary">{(page - 1) * limit + 1}</span> to{' '}
              <span className="font-medium text-text-primary">
                {Math.min(page * limit, total)}
              </span>{' '}
              of <span className="font-medium text-text-primary">{total}</span> tickets
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="p-1.5 rounded-lg border border-surface-border hover:bg-surface-elevated text-text-primary disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="px-2 font-medium text-text-primary">
                Page {page} of {totalPages}
              </span>
              <button
                type="button"
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="p-1.5 rounded-lg border border-surface-border hover:bg-surface-elevated text-text-primary disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Ticket Detail & Triage Modal */}
      {selectedTicketId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-fade-in">
          <div className="bg-surface-card border border-surface-border rounded-2xl w-full max-w-4xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden">
            {/* Modal Header */}
            <div className="p-5 border-b border-surface-border flex items-center justify-between bg-surface-elevated/50">
              <div className="flex items-center gap-3">
                <span className="font-mono text-sm font-bold text-primary">
                  {ticketDetail?.ticket.ticket_number || 'Loading...'}
                </span>
                {ticketDetail && (
                  <span
                    className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border ${
                      STATUS_CONFIG[ticketDetail.ticket.status]?.badgeClass || ''
                    }`}
                  >
                    <span
                      className={`w-1.5 h-1.5 rounded-full ${
                        STATUS_CONFIG[ticketDetail.ticket.status]?.dotClass || ''
                      }`}
                    />
                    {STATUS_CONFIG[ticketDetail.ticket.status]?.label || ticketDetail.ticket.status}
                  </span>
                )}
                {ticketDetail?.ticket.category && (
                  <span className="hidden sm:inline-block px-2.5 py-0.5 rounded-full text-xs font-medium bg-surface border border-surface-border text-text-secondary">
                    {ticketDetail.ticket.category}
                  </span>
                )}
              </div>

              <div className="flex items-center gap-2">
                {/* Status Switcher Dropdown */}
                {ticketDetail && (
                  <div className="relative">
                    <select
                      value={ticketDetail.ticket.status}
                      onChange={(e) => handleStatusChange(e.target.value)}
                      disabled={isUpdatingStatus}
                      className="px-3 py-1.5 bg-surface border border-surface-border rounded-lg text-xs font-medium text-text-primary focus:outline-none focus:border-primary cursor-pointer disabled:opacity-50"
                    >
                      <option value="open">Set Status: Open</option>
                      <option value="in_progress">Set Status: In Progress</option>
                      <option value="waiting_response">Set Status: Waiting on Participant</option>
                      <option value="resolved">Set Status: Resolved</option>
                      <option value="closed">Set Status: Closed</option>
                    </select>
                  </div>
                )}

                <button
                  type="button"
                  onClick={closeTicketDetail}
                  className="p-1.5 text-text-muted hover:text-text-primary rounded-lg hover:bg-surface-elevated transition-colors"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* Modal Body */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {isDetailLoading ? (
                <div className="py-20 text-center text-text-muted">
                  <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-primary" />
                  <span>Loading request details and discussion history...</span>
                </div>
              ) : detailError ? (
                <div className="p-4 bg-rose-500/10 border border-rose-500/20 rounded-xl text-xs text-rose-400">
                  {detailError}
                </div>
              ) : ticketDetail ? (
                <>
                  {/* Participant & Context Info Banner */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 p-4 bg-surface rounded-xl border border-surface-border text-xs">
                    <div>
                      <span className="text-text-muted block text-[11px]">Participant</span>
                      <span className="font-semibold text-text-primary block mt-0.5">
                        {ticketDetail.ticket.participant_name || 'Anonymous Participant'}
                      </span>
                      <span className="text-text-muted font-mono text-[11px]">
                        {ticketDetail.ticket.participant_email}
                      </span>
                    </div>

                    <div>
                      <span className="text-text-muted block text-[11px]">Registered Team</span>
                      <span className="font-semibold text-text-primary block mt-0.5">
                        {ticketDetail.ticket.team_name}
                      </span>
                      {ticketDetail.ticket.hackathon_title && (
                        <span className="text-text-muted text-[11px] block mt-0.5 line-clamp-1">
                          {ticketDetail.ticket.hackathon_title}
                        </span>
                      )}
                    </div>

                    <div>
                      <span className="text-text-muted block text-[11px]">
                        Venue & Physical Seating
                      </span>
                      {ticketDetail.ticket.category === 'Venue / Seating Query' ? (
                        <span className="font-semibold text-amber-400 block mt-0.5">
                          Team #{ticketDetail.ticket.team_number || 'N/A'}
                        </span>
                      ) : (
                        <div className="mt-0.5 space-y-0.5">
                          <span className="font-semibold text-primary block">
                            {ticketDetail.ticket.block_number || 'No block assigned'}
                          </span>
                          <span className="text-text-muted block text-[11px]">
                            {ticketDetail.ticket.lab_number
                              ? `Lab: ${ticketDetail.ticket.lab_number}`
                              : 'No lab specified'}
                          </span>
                        </div>
                      )}
                    </div>

                    <div>
                      <span className="text-text-muted block text-[11px]">Timestamps</span>
                      <span className="text-text-primary block mt-0.5">
                        Created: {formatDate(ticketDetail.ticket.created_at)}
                      </span>
                      <span className="text-text-muted text-[11px] block mt-0.5">
                        Updated: {formatDate(ticketDetail.ticket.updated_at)}
                      </span>
                    </div>
                  </div>

                  {/* Subject & Initial Issue Description */}
                  <div className="p-5 bg-surface rounded-xl border border-surface-border space-y-3">
                    <div className="flex items-center justify-between border-b border-surface-border/50 pb-2.5">
                      <h3 className="text-sm font-bold text-text-primary">
                        {ticketDetail.ticket.subject}
                      </h3>
                      <span className="text-[11px] text-text-muted font-medium px-2 py-0.5 bg-surface-elevated rounded">
                        {ticketDetail.ticket.category}
                      </span>
                    </div>
                    <div className="text-xs text-text-secondary whitespace-pre-wrap leading-relaxed">
                      {ticketDetail.ticket.description}
                    </div>

                    {/* Attachment Card if present */}
                    {ticketDetail.ticket.attachment_url && (
                      <div className="mt-4 pt-3 border-t border-surface-border/50 flex items-center justify-between p-3 bg-surface-elevated/50 rounded-lg">
                        <div className="flex items-center gap-2.5">
                          <Paperclip className="w-4 h-4 text-primary" />
                          <div>
                            <span className="text-xs font-semibold text-text-primary block">
                              {ticketDetail.ticket.attachment_name || 'Diagnostic Attachment'}
                            </span>
                            <span className="text-[11px] text-text-muted block">
                              Uploaded by participant
                            </span>
                          </div>
                        </div>
                        <a
                          href={api.getAdminSupportTicketAttachmentUrl(ticketDetail.ticket.id)}
                          target="_blank"
                          rel="noreferrer"
                          className="flex items-center gap-1.5 px-3 py-1.5 bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 rounded-lg text-xs font-medium transition-colors"
                        >
                          <ExternalLink className="w-3.5 h-3.5" />
                          <span>View Attachment</span>
                        </a>
                      </div>
                    )}
                  </div>

                  {/* Conversation Replies Thread */}
                  <div className="space-y-4">
                    <h4 className="text-xs font-bold text-text-muted uppercase tracking-wider flex items-center gap-2">
                      <MessageSquare className="w-3.5 h-3.5" />
                      <span>Discussion History ({ticketDetail.replies.length})</span>
                    </h4>

                    <div className="space-y-3">
                      {ticketDetail.replies.map((reply: SupportReplyItem) => {
                        return (
                          <div
                            key={reply.id}
                            className={`p-4 rounded-xl border text-xs leading-relaxed transition-all ${
                              reply.is_staff
                                ? 'bg-primary/5 border-primary/20 ml-4 sm:ml-8'
                                : 'bg-surface border-surface-border mr-4 sm:mr-8'
                            }`}
                          >
                            <div className="flex items-center justify-between mb-2">
                              <div className="flex items-center gap-2">
                                {reply.is_staff ? (
                                  <div className="w-6 h-6 rounded-full bg-primary/20 text-primary flex items-center justify-center font-bold text-[10px]">
                                    <ShieldCheck className="w-3.5 h-3.5" />
                                  </div>
                                ) : (
                                  <div className="w-6 h-6 rounded-full bg-surface-elevated text-text-muted flex items-center justify-center font-bold text-[10px]">
                                    <User className="w-3.5 h-3.5" />
                                  </div>
                                )}
                                <span
                                  className={`font-semibold ${
                                    reply.is_staff ? 'text-primary' : 'text-text-primary'
                                  }`}
                                >
                                  {reply.author_name}
                                </span>
                                {reply.is_staff && (
                                  <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-primary/20 text-primary">
                                    STAFF
                                  </span>
                                )}
                              </div>
                              <span className="text-[11px] text-text-muted">
                                {formatDate(reply.created_at)}
                              </span>
                            </div>
                            <div className="text-text-secondary whitespace-pre-wrap pl-8">
                              {reply.message}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* Super Admin Reply Box */}
                  <div className="p-4 bg-surface rounded-xl border border-surface-border space-y-3">
                    <h4 className="text-xs font-bold text-text-primary flex items-center gap-2">
                      <Send className="w-3.5 h-3.5 text-primary" />
                      <span>Post Administrator Response</span>
                    </h4>
                    <textarea
                      rows={4}
                      value={replyMessage}
                      onChange={(e) => setReplyMessage(e.target.value)}
                      placeholder="Type official guidance or resolution details here for the participant..."
                      className="w-full p-3 bg-surface-elevated border border-surface-border rounded-xl text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:border-primary transition-colors resize-y"
                    />

                    <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
                      <div className="text-[11px] text-text-muted">
                        Replying will notify the participant in their portal.
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => handleSendReply('waiting_response')}
                          disabled={!replyMessage.trim() || isSendingReply}
                          className="px-3 py-1.5 bg-surface-elevated hover:bg-surface-hover border border-surface-border text-text-primary font-medium rounded-lg text-xs transition-colors disabled:opacity-40"
                        >
                          Reply & Await User
                        </button>
                        <button
                          type="button"
                          onClick={() => handleSendReply('resolved')}
                          disabled={!replyMessage.trim() || isSendingReply}
                          className="px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white font-medium rounded-lg text-xs transition-colors disabled:opacity-40 flex items-center gap-1.5"
                        >
                          <CheckCircle2 className="w-3.5 h-3.5" />
                          <span>Reply & Resolve</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => handleSendReply()}
                          disabled={!replyMessage.trim() || isSendingReply}
                          className="px-4 py-1.5 bg-primary hover:bg-primary-hover text-white font-medium rounded-lg text-xs transition-colors disabled:opacity-40 flex items-center gap-1.5"
                        >
                          <Send className="w-3.5 h-3.5" />
                          <span>{isSendingReply ? 'Sending...' : 'Send Reply'}</span>
                        </button>
                      </div>
                    </div>
                  </div>
                </>
              ) : null}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
