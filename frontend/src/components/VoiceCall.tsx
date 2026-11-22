import { useEffect, useRef, useState } from 'react';
import {
  BarVisualizer,
  LiveKitRoom,
  RoomAudioRenderer,
  StartAudio,
  useLocalParticipant,
  useRoomContext,
  useTranscriptions,
  useVoiceAssistant,
} from '@livekit/components-react';
import { support } from '../services/api';
import type { LiveKitTokenResponse } from '../types/api';
import ErrorAlert from './ErrorAlert';

interface VoiceCallProps {
  /** Called when the call ends, with the support session that was logged for it */
  onEnd: (sessionId: number | null) => void;
}

const STATE_LABELS: Record<string, string> = {
  disconnected: 'Disconnected',
  connecting: 'Connecting to support…',
  'pre-connect-buffering': 'Connecting to support…',
  initializing: 'Agent is joining…',
  idle: 'Waiting for the agent…',
  listening: 'Listening',
  thinking: 'Thinking…',
  speaking: 'Speaking',
  failed: 'Agent failed to join',
};

/**
 * Live voice call with the LiveKit support agent.
 * Fetches a room token from the backend (which also dispatches the agent), then joins the room
 * with the microphone on and plays the agent's audio.
 */
export default function VoiceCall({ onEnd }: VoiceCallProps) {
  const [connection, setConnection] = useState<LiveKitTokenResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const endedRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    support
      .livekitToken()
      .then((data) => !cancelled && setConnection(data))
      .catch((err: Error) => !cancelled && setError(err.message));
    return () => {
      cancelled = true;
    };
  }, []);

  const finish = () => {
    if (endedRef.current) return;
    endedRef.current = true;
    onEnd(connection?.session_id ?? null);
  };

  if (error) {
    return (
      <div className="p-6 space-y-4">
        <ErrorAlert message={error} />
        <button onClick={() => onEnd(null)} className="text-sm font-medium text-primary-700 hover:underline">
          Back to chat
        </button>
      </div>
    );
  }

  if (!connection) {
    return (
      <div className="p-10 text-center text-gray-600">
        <div className="mx-auto mb-4 w-10 h-10 border-4 border-primary-600 border-t-transparent rounded-full animate-spin" />
        Starting your call…
      </div>
    );
  }

  return (
    <LiveKitRoom
      serverUrl={connection.server_url}
      token={connection.token}
      connect
      audio
      video={false}
      onDisconnected={finish}
      onError={(err) => setError(err.message)}
      onMediaDeviceFailure={() => setError('Microphone access was blocked. Allow the microphone and try again.')}
      className="flex flex-col h-full"
    >
      <CallPanel />
      <RoomAudioRenderer />
    </LiveKitRoom>
  );
}

function CallPanel() {
  const room = useRoomContext();
  const { state, audioTrack } = useVoiceAssistant();
  const { localParticipant, isMicrophoneEnabled } = useLocalParticipant();
  const transcriptions = useTranscriptions();
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [transcriptions]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex flex-col items-center gap-3 pt-8 pb-6 border-b border-gray-100 bg-gradient-to-b from-primary-50 to-white">
        <BarVisualizer state={state} track={audioTrack} barCount={5} className="voice-visualizer" />
        <p className="text-sm font-medium text-gray-700" aria-live="polite">
          {STATE_LABELS[state] ?? state}
        </p>
        <StartAudio
          label="Click to enable the agent's audio"
          className="text-xs px-3 py-1.5 rounded-full bg-amber-100 text-amber-800"
        />
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-4 space-y-3" aria-label="Live transcript">
        {transcriptions.length === 0 && (
          <p className="text-center text-sm text-gray-400 pt-6">
            The live transcript appears here. Try “Where is my order 10023?”
          </p>
        )}
        {transcriptions.map((t) => {
          const isUser = t.participantInfo.identity === localParticipant.identity;
          return (
            <div key={t.streamInfo.id} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
              <div
                className={`max-w-[80%] rounded-2xl px-4 py-2 text-sm leading-relaxed ${
                  isUser ? 'bg-primary-600 text-white rounded-br-md' : 'bg-gray-100 text-gray-800 rounded-bl-md'
                }`}
              >
                {t.text}
              </div>
            </div>
          );
        })}
      </div>

      <div className="flex justify-center gap-3 p-4 border-t border-gray-100">
        <button
          onClick={() => localParticipant.setMicrophoneEnabled(!isMicrophoneEnabled)}
          className={`px-5 py-2.5 rounded-full text-sm font-medium border transition-colors ${
            isMicrophoneEnabled
              ? 'border-gray-300 text-gray-700 hover:bg-gray-50'
              : 'border-amber-300 bg-amber-50 text-amber-800'
          }`}
          aria-pressed={!isMicrophoneEnabled}
        >
          {isMicrophoneEnabled ? 'Mute' : 'Unmute'}
        </button>
        <button
          onClick={() => room.disconnect()}
          className="px-5 py-2.5 rounded-full text-sm font-medium bg-red-600 text-white hover:bg-red-700 transition-colors"
        >
          End call
        </button>
      </div>
    </div>
  );
}
