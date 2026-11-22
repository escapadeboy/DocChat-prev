import { useState, useEffect, useRef } from 'react';
import type { VoiceSettings as VoiceSettingsType } from '../hooks/useVoiceSettings';
import { voice } from '../services/api';

interface VoiceSettingsProps {
  isOpen: boolean;
  onClose: () => void;
  settings: VoiceSettingsType;
  onUpdateSettings: (settings: Partial<VoiceSettingsType>) => void;
}

const VOICE_OPTIONS: Array<{ value: VoiceSettingsType['ttsVoice']; label: string; description: string }> = [
  { value: 'alloy', label: 'Alloy', description: 'Neutral and balanced' },
  { value: 'echo', label: 'Echo', description: 'Warm and engaging' },
  { value: 'fable', label: 'Fable', description: 'Expressive and dynamic' },
  { value: 'onyx', label: 'Onyx', description: 'Deep and authoritative' },
  { value: 'nova', label: 'Nova', description: 'Energetic and bright' },
  { value: 'shimmer', label: 'Shimmer', description: 'Soft and gentle' },
];

const LANGUAGE_OPTIONS = [
  { value: 'en', label: 'English' },
  { value: 'es', label: 'Spanish' },
  { value: 'fr', label: 'French' },
  { value: 'de', label: 'German' },
  { value: 'it', label: 'Italian' },
  { value: 'pt', label: 'Portuguese' },
  { value: 'zh', label: 'Chinese' },
  { value: 'ja', label: 'Japanese' },
  { value: 'ko', label: 'Korean' },
  { value: 'ar', label: 'Arabic' },
];

/**
 * VoiceSettings Modal Component
 * 
 * Features:
 * - TTS voice selection with preview
 * - Auto-play toggle
 * - Input language selection
 * - localStorage persistence
 * - Accessible modal with keyboard support
 */
export default function VoiceSettings({
  isOpen,
  onClose,
  settings,
  onUpdateSettings
}: VoiceSettingsProps) {
  const [playingVoice, setPlayingVoice] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const modalRef = useRef<HTMLDivElement>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Handle ESC key to close
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
      // Prevent body scroll when modal is open
      document.body.style.overflow = 'hidden';
    }

    return () => {
      document.removeEventListener('keydown', handleEscape);
      document.body.style.overflow = '';
    };
  }, [isOpen, onClose]);

  // Cleanup audio on unmount
  useEffect(() => {
    return () => {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
      }
    };
  }, []);

  // Handle click outside to close
  const handleOverlayClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  const playVoicePreview = async (voiceName: string) => {
    setPreviewError(null);
    
    // Stop any currently playing audio
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }

    try {
      setPlayingVoice(voiceName);
      const sampleText = `Hello! This is a preview of the ${voiceName} voice.`;
      const audioBlob = await voice.speak(sampleText, voiceName);
      const audioUrl = URL.createObjectURL(audioBlob);
      const audio = new Audio(audioUrl);
      audioRef.current = audio;

      audio.onended = () => {
        setPlayingVoice(null);
        URL.revokeObjectURL(audioUrl);
        audioRef.current = null;
      };

      audio.onerror = () => {
        setPlayingVoice(null);
        setPreviewError('Failed to play preview');
        URL.revokeObjectURL(audioUrl);
        audioRef.current = null;
      };

      await audio.play();
    } catch (error: any) {
      setPlayingVoice(null);
      setPreviewError(error.message || 'Failed to generate voice preview');
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm animate-fadeIn"
      onClick={handleOverlayClick}
      role="dialog"
      aria-modal="true"
      aria-labelledby="voice-settings-title"
    >
      <div
        ref={modalRef}
        className="bg-white rounded-xl shadow-2xl max-w-lg w-full max-h-[90vh] overflow-y-auto animate-slideUp"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-200">
          <h2 id="voice-settings-title" className="text-xl font-bold text-gray-900">
            Voice Settings
          </h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
            aria-label="Close settings"
          >
            <svg className="w-5 h-5 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="p-6 space-y-6">
          {/* TTS Voice Selection */}
          <div>
            <label className="block text-sm font-semibold text-gray-900 mb-1">
              Text-to-Speech Voice
            </label>
            <p className="text-xs text-gray-600 mb-3">
              Choose the voice for reading bot responses
            </p>
            <div className="space-y-2">
              {VOICE_OPTIONS.map((voiceOption) => (
                <div
                  key={voiceOption.value}
                  className={`flex items-center justify-between p-3 border rounded-lg transition-all cursor-pointer ${
                    settings.ttsVoice === voiceOption.value
                      ? 'border-primary-500 bg-primary-50'
                      : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                  }`}
                  onClick={() => onUpdateSettings({ ttsVoice: voiceOption.value })}
                >
                  <div className="flex items-center gap-3 flex-1">
                    <input
                      type="radio"
                      name="voice"
                      value={voiceOption.value}
                      checked={settings.ttsVoice === voiceOption.value}
                      onChange={() => onUpdateSettings({ ttsVoice: voiceOption.value })}
                      className="w-4 h-4 text-primary-600 focus:ring-primary-500"
                    />
                    <div>
                      <div className="text-sm font-medium text-gray-900">{voiceOption.label}</div>
                      <div className="text-xs text-gray-600">{voiceOption.description}</div>
                    </div>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      playVoicePreview(voiceOption.value);
                    }}
                    disabled={playingVoice === voiceOption.value}
                    className="p-2 hover:bg-white rounded-lg transition-colors disabled:opacity-50"
                    aria-label={`Preview ${voiceOption.label} voice`}
                  >
                    {playingVoice === voiceOption.value ? (
                      <svg className="w-5 h-5 text-primary-600 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" />
                      </svg>
                    ) : (
                      <svg className="w-5 h-5 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                    )}
                  </button>
                </div>
              ))}
            </div>
            {previewError && (
              <p className="mt-2 text-xs text-red-600">{previewError}</p>
            )}
          </div>

          {/* Auto-play Toggle */}
          <div>
            <label className="flex items-center justify-between cursor-pointer">
              <div>
                <div className="text-sm font-semibold text-gray-900">Auto-play Responses</div>
                <p className="text-xs text-gray-600 mt-1">
                  Automatically play audio for bot messages
                </p>
              </div>
              <div className="relative">
                <input
                  type="checkbox"
                  checked={settings.autoPlay}
                  onChange={(e) => onUpdateSettings({ autoPlay: e.target.checked })}
                  className="sr-only peer"
                  aria-label="Toggle auto-play"
                />
                <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-primary-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary-600"></div>
              </div>
            </label>
          </div>

          {/* Input Language */}
          <div>
            <label htmlFor="language-select" className="block text-sm font-semibold text-gray-900 mb-1">
              Input Language
            </label>
            <p className="text-xs text-gray-600 mb-3">
              Language for voice recognition and transcription
            </p>
            <select
              id="language-select"
              value={settings.inputLanguage}
              onChange={(e) => onUpdateSettings({ inputLanguage: e.target.value })}
              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-gray-900 bg-white"
            >
              {LANGUAGE_OPTIONS.map((lang) => (
                <option key={lang.value} value={lang.value}>
                  {lang.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Footer */}
        <div className="p-6 border-t border-gray-200 bg-gray-50 rounded-b-xl">
          <button
            onClick={onClose}
            className="w-full px-6 py-3 bg-gradient-to-r from-slate-800 to-slate-900 hover:from-slate-700 hover:to-slate-800 text-white rounded-xl font-semibold shadow-md hover:shadow-lg transition-all duration-200"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}

