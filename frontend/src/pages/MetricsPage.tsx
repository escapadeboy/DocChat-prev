import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { support } from '../services/api';
import type { LatencyStats, SupportMetrics } from '../types/api';
import LoadingSpinner from '../components/LoadingSpinner';
import ErrorAlert from '../components/ErrorAlert';

const fmtMs = (ms: number | null) => (ms === null ? '—' : ms >= 1000 ? `${(ms / 1000).toFixed(2)} s` : `${Math.round(ms)} ms`);
const pct = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${v.toFixed(1)}%`);

/** Evaluation dashboard for the four capstone metrics plus supporting distributions. */
export default function MetricsPage() {
  const [metrics, setMetrics] = useState<SupportMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => support.metrics().then(setMetrics).catch((err) => setError(err.message));
  useEffect(() => {
    load();
  }, []);

  if (error) return <div className="max-w-6xl mx-auto px-4 py-8"><ErrorAlert message={error} /></div>;
  if (!metrics) return <LoadingSpinner />;

  const acc = metrics.intent_accuracy;
  const llm = acc?.llm;
  const baseline = acc?.baseline;

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Bot evaluation</h1>
          <p className="text-sm text-gray-500 mt-1">
            {metrics.volume.sessions} conversations · {metrics.volume.user_turns} customer turns ·{' '}
            {metrics.volume.sessions_by_channel.text ?? 0} text / {metrics.volume.sessions_by_channel.voice ?? 0} voice
          </p>
        </div>
        <button onClick={load} className="text-sm px-3 py-1.5 rounded-lg border border-gray-300 hover:bg-gray-50">Refresh</button>
      </div>

      {/* The four evaluation metrics */}
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-label="Evaluation metrics">
        <StatTile
          title="Intent accuracy"
          value={llm ? pct(llm.accuracy * 100) : '—'}
          detail={
            llm
              ? `LLM, macro-F1 ${llm.macro_f1.toFixed(2)}, n=${llm.test_size}` + (baseline ? ` · TF-IDF baseline ${pct(baseline.accuracy * 100)}` : '')
              : 'Run python eval/evaluate_intents.py'
          }
        />
        <StatTile
          title="Response appropriateness"
          value={metrics.appropriateness ? `${metrics.appropriateness.overall.toFixed(2)} / 5` : '—'}
          detail={
            metrics.appropriateness
              ? Object.entries(metrics.appropriateness.scores).map(([k, v]) => `${k} ${v.toFixed(1)}`).join(' · ') +
                ` · ${metrics.appropriateness.reviewed_turns} turns reviewed`
              : 'Run eval/export_for_review.py and score the CSV'
          }
        />
        <StatTile
          title="Avg response time"
          value={fmtMs(metrics.response_time.all.mean_ms)}
          detail={`Text ${fmtMs(metrics.response_time.text.mean_ms)} · Voice ${fmtMs(metrics.response_time.voice.mean_ms)}`}
        />
        <StatTile
          title="User satisfaction"
          value={metrics.satisfaction.all.average_rating !== null ? `${metrics.satisfaction.all.average_rating.toFixed(2)} / 5` : '—'}
          detail={`${metrics.satisfaction.all.count} ratings · ${pct(metrics.satisfaction.all.resolved_pct)} resolved`}
        />
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Response time by channel" note="Text: request to reply. Voice: end of speech to agent speaking.">
          <LatencyTable rows={{ Text: metrics.response_time.text, Voice: metrics.response_time.voice, All: metrics.response_time.all }} />
        </Panel>

        <Panel title="Satisfaction ratings" note="Number of feedback forms per star rating.">
          <HorizontalBars
            data={['5', '4', '3', '2', '1'].map((k) => ({ label: `${k} ★`, value: metrics.satisfaction.all.distribution[k] ?? 0 }))}
            unit="ratings"
          />
          <p className="mt-3 text-xs text-gray-500">
            Text {metrics.satisfaction.text.average_rating?.toFixed(2) ?? '—'} ({metrics.satisfaction.text.count}) · Voice{' '}
            {metrics.satisfaction.voice.average_rating?.toFixed(2) ?? '—'} ({metrics.satisfaction.voice.count})
          </p>
        </Panel>

        <Panel title="Detected intents" note="Customer turns by intent (live conversations).">
          <HorizontalBars
            data={Object.entries(metrics.intent_distribution).map(([label, value]) => ({ label: label.replace(/_/g, ' '), value }))}
            unit="turns"
          />
        </Panel>

        <Panel title="Sentiment & escalation" note="Escalation: sentiment at or below −0.7, asking for a human, or 3 out-of-scope turns in a row.">
          <HorizontalBars
            data={['positive', 'neutral', 'negative'].map((k) => ({ label: k, value: metrics.sentiment_distribution[k] ?? 0 }))}
            unit="turns"
          />
          <dl className="mt-4 grid grid-cols-3 gap-3 text-center">
            <MiniStat label="Escalation rate" value={pct(metrics.escalation.rate_pct)} />
            <MiniStat label="Open tickets" value={String(metrics.escalation.open_tickets)} />
            <MiniStat label="Avg sentiment" value={metrics.average_sentiment?.toFixed(2) ?? '—'} />
          </dl>
        </Panel>

        {acc && llm && baseline && (
          <Panel title="Intent classifier comparison" note={`Held-out test set, evaluated ${acc.evaluated_at ? new Date(acc.evaluated_at).toLocaleDateString() : ''}.`}>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-gray-500 border-b border-gray-100">
                  <th className="py-2 font-medium">Classifier</th>
                  <th className="py-2 font-medium text-right">Accuracy</th>
                  <th className="py-2 font-medium text-right">Macro-F1</th>
                </tr>
              </thead>
              <tbody className="text-gray-800">
                <tr className="border-b border-gray-50">
                  <td className="py-2">LLM (structured output)</td>
                  <td className="py-2 text-right tabular-nums">{pct(llm.accuracy * 100)}</td>
                  <td className="py-2 text-right tabular-nums">{llm.macro_f1.toFixed(3)}</td>
                </tr>
                <tr>
                  <td className="py-2">TF-IDF + logistic regression</td>
                  <td className="py-2 text-right tabular-nums">{pct(baseline.accuracy * 100)}</td>
                  <td className="py-2 text-right tabular-nums">{baseline.macro_f1.toFixed(3)}</td>
                </tr>
              </tbody>
            </table>
          </Panel>
        )}
      </div>
    </div>
  );
}

function StatTile({ title, value, detail }: { title: string; value: string; detail: string }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
      <p className="text-xs font-medium uppercase tracking-wide text-gray-500">{title}</p>
      <p className="mt-2 text-3xl font-semibold text-gray-900 tabular-nums">{value}</p>
      <p className="mt-2 text-xs text-gray-500 leading-relaxed">{detail}</p>
    </div>
  );
}

function Panel({ title, note, children }: { title: string; note?: string; children: ReactNode }) {
  return (
    <section className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
      <h2 className="text-sm font-semibold text-gray-900">{title}</h2>
      {note && <p className="text-xs text-gray-500 mt-0.5 mb-4">{note}</p>}
      {children}
    </section>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-gray-500">{label}</dt>
      <dd className="text-lg font-semibold text-gray-900 tabular-nums">{value}</dd>
    </div>
  );
}

/** Single-series horizontal bars: one hue, value labels in text ink, hover tooltip per bar. */
function HorizontalBars({ data, unit }: { data: { label: string; value: number }[]; unit: string }) {
  const max = Math.max(1, ...data.map((d) => d.value));
  const total = data.reduce((s, d) => s + d.value, 0);
  if (total === 0) return <p className="text-sm text-gray-400 py-4">No data yet.</p>;
  return (
    <ul className="space-y-2">
      {data.map((d) => (
        <li key={d.label} className="group grid grid-cols-[7.5rem_1fr_3rem] items-center gap-3 text-sm" title={`${d.label}: ${d.value} ${unit} (${((100 * d.value) / total).toFixed(0)}%)`}>
          <span className="truncate text-gray-600 capitalize">{d.label}</span>
          <span className="h-3 rounded-r bg-gray-50">
            <span
              className="block h-full rounded-r bg-primary-600 group-hover:bg-primary-700 transition-colors"
              style={{ width: `${(100 * d.value) / max}%`, minWidth: d.value ? '4px' : 0 }}
            />
          </span>
          <span className="text-right tabular-nums text-gray-800">{d.value}</span>
        </li>
      ))}
    </ul>
  );
}

function LatencyTable({ rows }: { rows: Record<string, LatencyStats> }) {
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-left text-xs text-gray-500 border-b border-gray-100">
          <th className="py-2 font-medium">Channel</th>
          <th className="py-2 font-medium text-right">Turns</th>
          <th className="py-2 font-medium text-right">Mean</th>
          <th className="py-2 font-medium text-right">Median</th>
          <th className="py-2 font-medium text-right">p95</th>
        </tr>
      </thead>
      <tbody className="text-gray-800">
        {Object.entries(rows).map(([name, s]) => (
          <tr key={name} className="border-b border-gray-50 last:border-0">
            <td className="py-2">{name}</td>
            <td className="py-2 text-right tabular-nums">{s.count}</td>
            <td className="py-2 text-right tabular-nums">{fmtMs(s.mean_ms)}</td>
            <td className="py-2 text-right tabular-nums">{fmtMs(s.p50_ms)}</td>
            <td className="py-2 text-right tabular-nums">{fmtMs(s.p95_ms)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
