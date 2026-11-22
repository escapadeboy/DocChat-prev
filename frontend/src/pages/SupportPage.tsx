import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { support } from '../services/api';
import type { Intent, OrderSummary, SupportChatResponse } from '../types/api';
import ErrorAlert from '../components/ErrorAlert';
import FeedbackForm from '../components/FeedbackForm';

// The LiveKit SDK is large; load it only when a call starts
const VoiceCall = lazy(() => import('../components/VoiceCall'));

interface Message {
  role: 'user' | 'assistant';
  content: string;
  analysis?: SupportChatResponse;
}

const INTENT_LABELS: Record<Intent, string> = {
  faq: 'FAQ',
  order_status: 'Order status',
  return_request: 'Return',
  cancel_order: 'Cancel order',
  product_info: 'Product info',
  talk_to_human: 'Human agent',
  complaint: 'Complaint',
  greeting: 'Greeting',
  other: 'Out of scope',
};

const SENTIMENT_STYLES = {
  positive: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  neutral: 'bg-gray-50 text-gray-600 border-gray-200',
  negative: 'bg-red-50 text-red-700 border-red-200',
};

const STATUS_STYLES: Record<OrderSummary['status'], string> = {
  placed: 'bg-blue-50 text-blue-700',
  shipped: 'bg-indigo-50 text-indigo-700',
  out_for_delivery: 'bg-amber-50 text-amber-800',
  delivered: 'bg-emerald-50 text-emerald-700',
  cancelled: 'bg-gray-100 text-gray-500',
};

const SUGGESTIONS = [
  'Where is my order ORD-10023?',
  "What's your return policy?",
  'I want to return the headphones from ORD-10021, they stopped working',
  'Cancel order ORD-10024',
  'Is the power bank in stock?',
  'This is ridiculous, I want to talk to a person!',
];

const WELCOME: Message = {
  role: 'assistant',
  content: "Hi! I'm the **ShopEase** support assistant. I can track orders, handle returns and cancellations, and answer questions about our policies. How can I help?",
};

export default function SupportPage() {
  const [messages, setMessages] = useState<Message[]>([WELCOME]);
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [orders, setOrders] = useState<OrderSummary[]>([]);
  const [inCall, setInCall] = useState(false);
  const [feedbackFor, setFeedbackFor] = useState<{ sessionId: number | null; channel: 'text' | 'voice' } | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const loadOrders = () => support.orders().then(setOrders).catch(() => setOrders([]));

  useEffect(() => {
    loadOrders();
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, sending]);

  const send = async (text: string) => {
    const message = text.trim();
    if (!message || sending) return;
    setInput('');
    setError(null);
    setMessages((prev) => [...prev, { role: 'user', content: message }]);
    setSending(true);
    try {
      const reply = await support.chat(message, sessionId);
      setSessionId(reply.session_id);
      // Attach the NLP analysis to the user's message it describes
      setMessages((prev) => {
        const next = [...prev];
        next[next.length - 1] = { ...next[next.length - 1], analysis: reply };
        return [...next, { role: 'assistant', content: reply.answer }];
      });
      loadOrders(); // a cancellation or return may have changed an order
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSending(false);
    }
  };

  const endChat = () => {
    if (sessionId) setFeedbackFor({ sessionId, channel: 'text' });
    setMessages([WELCOME]);
    setSessionId(null);
  };

  const endCall = (voiceSessionId: number | null) => {
    setInCall(false);
    loadOrders();
    if (voiceSessionId) setFeedbackFor({ sessionId: voiceSessionId, channel: 'voice' });
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
      <div className="flex flex-col lg:flex-row gap-6">
        {/* Conversation */}
        <section className="flex-1 min-w-0 bg-white rounded-2xl shadow-md border border-gray-200 flex flex-col h-[calc(100vh-9rem)] min-h-[520px]">
          <header className="flex items-center justify-between gap-3 px-5 py-4 border-b border-gray-100">
            <div className="min-w-0">
              <h1 className="text-lg font-semibold text-gray-900">Customer Support</h1>
              <p className="text-xs text-gray-500">{inCall ? 'Live voice call' : 'Chat or call our AI assistant'}</p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {!inCall && sessionId && (
                <button onClick={endChat} className="px-3 py-2 rounded-lg text-sm text-gray-600 hover:bg-gray-100">
                  End chat
                </button>
              )}
              {!inCall && (
                <button
                  onClick={() => setInCall(true)}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-primary-600 text-white hover:bg-primary-700 transition-colors"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                  </svg>
                  Call support
                </button>
              )}
            </div>
          </header>

          {inCall ? (
            <div className="flex-1 min-h-0">
              <Suspense fallback={<p className="p-10 text-center text-gray-600">Loading voice call…</p>}>
                <VoiceCall onEnd={endCall} />
              </Suspense>
            </div>
          ) : (
            <>
              <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-5 space-y-4">
                {messages.map((m, i) => (
                  <MessageBubble key={i} message={m} />
                ))}
                {sending && (
                  <div className="flex gap-1.5 px-4 py-3 bg-gray-100 rounded-2xl rounded-bl-md w-fit" aria-label="Assistant is typing">
                    {[0, 150, 300].map((d) => (
                      <span key={d} className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: `${d}ms` }} />
                    ))}
                  </div>
                )}
                {messages.length === 1 && (
                  <div className="flex flex-wrap gap-2 pt-2">
                    {SUGGESTIONS.map((s) => (
                      <button
                        key={s}
                        onClick={() => send(s)}
                        className="text-left text-sm px-3 py-1.5 rounded-full border border-primary-200 text-primary-800 bg-primary-50 hover:bg-primary-100 transition-colors"
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {error && (
                <div className="px-5 pb-2">
                  <ErrorAlert message={error} onClose={() => setError(null)} />
                </div>
              )}

              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  send(input);
                }}
                className="flex gap-2 p-4 border-t border-gray-100"
              >
                <label htmlFor="support-input" className="sr-only">Message</label>
                <input
                  id="support-input"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="Ask about an order, a return, or our policies…"
                  maxLength={2000}
                  className="flex-1 min-w-0 rounded-xl border border-gray-300 px-4 py-2.5 text-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none"
                />
                <button
                  type="submit"
                  disabled={!input.trim() || sending}
                  className="px-5 py-2.5 rounded-xl text-sm font-medium bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Send
                </button>
              </form>
            </>
          )}
        </section>

        {/* Orders panel */}
        <aside className="lg:w-80 shrink-0">
          <div className="bg-white rounded-2xl shadow-md border border-gray-200 p-5 lg:sticky lg:top-24 lg:max-h-[calc(100vh-9rem)] lg:overflow-y-auto">
            <h2 className="text-sm font-semibold text-gray-900">Your orders</h2>
            {orders.length === 0 ? (
              <p className="mt-3 text-sm text-gray-500">No orders yet. Run <code className="text-xs">seed_ecommerce.py</code> to add demo orders.</p>
            ) : (
              <ul className="mt-3 space-y-3">
                {orders.map((o) => (
                  <li key={o.order_number} className="rounded-xl border border-gray-100 p-3">
                    <div className="flex items-center justify-between gap-2">
                      <button
                        onClick={() => !inCall && setInput(`Where is my order ${o.order_number}?`)}
                        className="font-mono text-sm font-medium text-gray-900 hover:text-primary-700"
                        title="Ask about this order"
                      >
                        {o.order_number}
                      </button>
                      <span className={`text-xs px-2 py-0.5 rounded-full ${STATUS_STYLES[o.status]}`}>
                        {o.status.replace(/_/g, ' ')}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-gray-600 truncate">{o.items.map((i) => i.product).join(', ')}</p>
                    <p className="mt-0.5 text-xs text-gray-400">
                      ₹{o.total.toLocaleString('en-IN')} · placed {o.placed_on}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </aside>
      </div>

      {feedbackFor && (
        <FeedbackForm sessionId={feedbackFor.sessionId} channel={feedbackFor.channel} onDone={() => setFeedbackFor(null)} />
      )}
    </div>
  );
}

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === 'user';
  const a = message.analysis;
  return (
    <div className={`flex flex-col ${isUser ? 'items-end' : 'items-start'}`}>
      <div
        className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm ${
          isUser ? 'bg-primary-600 text-white rounded-br-md' : 'bg-gray-100 text-gray-800 rounded-bl-md'
        }`}
      >
        {isUser ? (
          message.content
        ) : (
          <ReactMarkdown
            components={{
              p: ({ children }) => <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>,
              ul: ({ children }) => <ul className="mb-2 ml-4 space-y-1 list-disc">{children}</ul>,
              ol: ({ children }) => <ol className="mb-2 ml-4 space-y-1 list-decimal">{children}</ol>,
              strong: ({ children }) => <strong className="font-semibold text-gray-900">{children}</strong>,
            }}
          >
            {message.content}
          </ReactMarkdown>
        )}
      </div>

      {/* NLP analysis of the user's turn: shown so the intent/entity/sentiment pipeline is visible in demos */}
      {a && (
        <div className="mt-1.5 flex flex-wrap justify-end gap-1.5 text-[11px]">
          <span className="px-2 py-0.5 rounded-full border border-primary-200 bg-primary-50 text-primary-800" title={`Classifier: ${a.classifier}`}>
            {INTENT_LABELS[a.intent]} · {Math.round(a.intent_confidence * 100)}%
          </span>
          <span className={`px-2 py-0.5 rounded-full border ${SENTIMENT_STYLES[a.sentiment_label]}`}>
            {a.sentiment_label} {a.sentiment_score > 0 ? '+' : ''}{a.sentiment_score.toFixed(2)}
          </span>
          {Object.entries(a.entities).map(([k, v]) => (
            <span key={k} className="px-2 py-0.5 rounded-full border border-gray-200 bg-white text-gray-600">
              {k.replace(/_/g, ' ')}: <span className="font-medium text-gray-800">{v}</span>
            </span>
          ))}
          <span className="px-2 py-0.5 text-gray-400">{(a.response_time_ms / 1000).toFixed(1)}s</span>
          {a.escalated && (
            <span className="px-2 py-0.5 rounded-full border border-amber-300 bg-amber-50 text-amber-800 font-medium">
              Escalated · ticket #{a.ticket_id}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
