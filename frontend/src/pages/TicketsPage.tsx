import { useEffect, useState } from 'react';
import { support } from '../services/api';
import type { SupportTicket } from '../types/api';
import LoadingSpinner from '../components/LoadingSpinner';
import ErrorAlert from '../components/ErrorAlert';

const PRIORITY_STYLES: Record<SupportTicket['priority'], string> = {
  urgent: 'bg-red-600 text-white',
  high: 'bg-orange-100 text-orange-800',
  normal: 'bg-blue-50 text-blue-700',
  low: 'bg-gray-100 text-gray-600',
};

// The API returns UTC timestamps, sometimes without a zone suffix (SQLite)
const formatTime = (iso: string) =>
  new Date(/(Z|[+-]\d\d:\d\d)$/.test(iso) ? iso : `${iso}Z`).toLocaleString();

/** Human-agent queue of conversations the bot escalated. */
export default function TicketsPage() {
  const [tickets, setTickets] = useState<SupportTicket[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showResolved, setShowResolved] = useState(false);

  const load = () =>
    support
      .tickets()
      .then(setTickets)
      .catch((err) => setError(err.message));

  useEffect(() => {
    load();
    const timer = setInterval(load, 15000);
    return () => clearInterval(timer);
  }, []);

  const update = async (id: number, status: SupportTicket['status']) => {
    await support.updateTicket(id, status);
    load();
  };

  const visible = (tickets ?? []).filter((t) => showResolved || t.status !== 'resolved');

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="flex flex-wrap items-end justify-between gap-3 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Escalation queue</h1>
          <p className="text-sm text-gray-500 mt-1">Conversations the bot handed to a human, most urgent first.</p>
        </div>
        <label className="flex items-center gap-2 text-sm text-gray-600">
          <input type="checkbox" checked={showResolved} onChange={(e) => setShowResolved(e.target.checked)} />
          Show resolved
        </label>
      </div>

      {error && <ErrorAlert message={error} onClose={() => setError(null)} />}
      {tickets === null && !error && <LoadingSpinner />}
      {tickets !== null && visible.length === 0 && (
        <p className="text-center text-gray-500 py-16">No open tickets. The bot is handling everything.</p>
      )}

      <ul className="space-y-3">
        {visible.map((t) => (
          <li key={t.id} className={`bg-white rounded-xl border border-gray-200 shadow-sm p-4 ${t.status === 'resolved' ? 'opacity-60' : ''}`}>
            <div className="flex flex-wrap items-center gap-2">
              <span className={`text-xs font-semibold uppercase tracking-wide px-2 py-0.5 rounded ${PRIORITY_STYLES[t.priority]}`}>
                {t.priority}
              </span>
              <span className="font-medium text-gray-900">#{t.id} · {t.customer}</span>
              <span className="text-xs text-gray-500">{t.customer_phone}</span>
              <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">{t.channel}</span>
              <span className="text-xs text-gray-400 ml-auto">{formatTime(t.created_at)}</span>
            </div>
            <p className="mt-2 text-sm text-gray-700"><span className="text-gray-500">Reason:</span> {t.reason}</p>
            {t.summary && t.summary !== t.reason && (
              <p className="mt-1 text-sm text-gray-600 italic">“{t.summary}”</p>
            )}
            <div className="mt-3 flex flex-wrap items-center gap-2">
              {t.sentiment_score !== null && (
                <span className="text-xs text-gray-500">Sentiment {t.sentiment_score.toFixed(2)}</span>
              )}
              <div className="ml-auto flex gap-2">
                {t.status === 'open' && (
                  <button onClick={() => update(t.id, 'assigned')} className="text-sm px-3 py-1.5 rounded-lg border border-gray-300 hover:bg-gray-50">
                    Assign to me
                  </button>
                )}
                {t.status !== 'resolved' ? (
                  <button onClick={() => update(t.id, 'resolved')} className="text-sm px-3 py-1.5 rounded-lg bg-primary-600 text-white hover:bg-primary-700">
                    Mark resolved
                  </button>
                ) : (
                  <button onClick={() => update(t.id, 'open')} className="text-sm px-3 py-1.5 rounded-lg border border-gray-300 hover:bg-gray-50">
                    Reopen
                  </button>
                )}
              </div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
