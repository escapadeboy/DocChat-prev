import { useState } from 'react';
import { support } from '../services/api';
import ErrorAlert from './ErrorAlert';

interface FeedbackFormProps {
  sessionId: number | null;
  channel: 'text' | 'voice';
  onDone: () => void;
}

const RATING_LABELS = ['', 'Very poor', 'Poor', 'Okay', 'Good', 'Excellent'];

/** Post-conversation satisfaction form (feeds the User Satisfaction Score metric). */
export default function FeedbackForm({ sessionId, channel, onDone }: FeedbackFormProps) {
  const [rating, setRating] = useState(0);
  const [hover, setHover] = useState(0);
  const [resolved, setResolved] = useState<boolean | null>(null);
  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await support.feedback({ session_id: sessionId, channel, rating, resolved, comment: comment || undefined });
      onDone();
    } catch (err) {
      setError((err as Error).message);
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="dialog" aria-modal="true" aria-labelledby="feedback-title">
      <div className="w-full max-w-md bg-white rounded-2xl shadow-2xl p-6 animate-slideUp">
        <h2 id="feedback-title" className="text-lg font-semibold text-gray-900">How did we do?</h2>
        <p className="text-sm text-gray-500 mt-1">Rate your {channel === 'voice' ? 'call' : 'chat'} with ShopEase support.</p>

        <div className="mt-5 flex items-center gap-1" onMouseLeave={() => setHover(0)}>
          {[1, 2, 3, 4, 5].map((n) => (
            <button
              key={n}
              onClick={() => setRating(n)}
              onMouseEnter={() => setHover(n)}
              aria-label={`${n} star${n > 1 ? 's' : ''}: ${RATING_LABELS[n]}`}
              aria-pressed={rating === n}
              className="p-1"
            >
              <svg className={`w-9 h-9 transition-colors ${(hover || rating) >= n ? 'text-amber-400' : 'text-gray-200'}`} fill="currentColor" viewBox="0 0 20 20">
                <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
              </svg>
            </button>
          ))}
          <span className="ml-2 text-sm text-gray-600">{RATING_LABELS[hover || rating]}</span>
        </div>

        <fieldset className="mt-5">
          <legend className="text-sm font-medium text-gray-700">Was your issue resolved?</legend>
          <div className="mt-2 flex gap-2">
            {[
              { label: 'Yes', value: true },
              { label: 'No', value: false },
            ].map((opt) => (
              <button
                key={opt.label}
                onClick={() => setResolved(opt.value)}
                aria-pressed={resolved === opt.value}
                className={`px-4 py-1.5 rounded-lg text-sm border transition-colors ${
                  resolved === opt.value ? 'bg-primary-600 border-primary-600 text-white' : 'border-gray-300 text-gray-700 hover:bg-gray-50'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </fieldset>

        <label className="block mt-5 text-sm font-medium text-gray-700" htmlFor="feedback-comment">
          Anything we could do better? <span className="font-normal text-gray-400">(optional)</span>
        </label>
        <textarea
          id="feedback-comment"
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          rows={3}
          maxLength={2000}
          className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none"
        />

        {error && <div className="mt-4"><ErrorAlert message={error} /></div>}

        <div className="mt-6 flex justify-end gap-2">
          <button onClick={onDone} className="px-4 py-2 rounded-lg text-sm text-gray-600 hover:bg-gray-100">
            Skip
          </button>
          <button
            onClick={submit}
            disabled={rating === 0 || submitting}
            className="px-4 py-2 rounded-lg text-sm font-medium bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? 'Sending…' : 'Submit feedback'}
          </button>
        </div>
      </div>
    </div>
  );
}
