import { useState, useRef, useEffect, useCallback } from 'react';
import { voice } from '../services/api';
import ErrorAlert from './ErrorAlert';

interface VoiceOutputProps {
  text: string;
  autoPlay?: boolean;
  voice?: 'alloy' | 'echo' | 'fable' | 'onyx' | 'nova' | 'shimmer';
  size?: 'sm' | 'md' | 'lg';
}

/**
 * VoiceOutput component for text-to-speech playback
 * 
 * Features:
 * - Click to play/pause audio
 * - Visual feedback for loading, playing, paused states
 * - Animated sound waves while playing
 * - Auto-play support
 * - Error handling with retry
 */
export default function VoiceOutput({
  text,
  autoPlay = false,
  voice: voiceOption = 'alloy',
  size = 'md'
}: VoiceOutputProps) {
  // State
  const [isLoading, setIsLoading] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);

  // Ref for audio element
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Size variant classes
  const sizeClasses = {
    sm: 'w-10 h-10 text-sm',
    md: 'w-12 h-12 text-base',
    lg: 'w-14 h-14 text-lg',
  };

  const iconSizes = {
    sm: 'w-5 h-5',
    md: 'w-6 h-6',
    lg: 'w-7 h-7',
  };

  // Fetch audio and set up playback
  const fetchAndPlayAudio = useCallback(async () => {
    if (!text || text.trim().length === 0) {
      setError('No text to speak');
      return;
    }

    try {
      setIsLoading(true);
      setError(null);

      // Call TTS API
      const audioBlob = await voice.speak(text, voiceOption);

      // Create blob URL
      const url = URL.createObjectURL(audioBlob);
      setAudioUrl(url);

      // Create and configure audio element
      const audio = new Audio(url);
      audioRef.current = audio;

      // Set up event listeners
      audio.onplay = () => {
        setIsPlaying(true);
        setIsPaused(false);
      };

      audio.onpause = () => {
        setIsPlaying(false);
        setIsPaused(true);
      };

      audio.onended = () => {
        setIsPlaying(false);
        setIsPaused(false);
      };

      audio.onerror = () => {
        setError('Failed to play audio');
        setIsPlaying(false);
        setIsPaused(false);
      };

      // Auto-play if requested
      if (autoPlay) {
        await audio.play();
      }
    } catch (err: any) {
      console.error('TTS error:', err);
      setError(err.message || 'Failed to generate speech');
    } finally {
      setIsLoading(false);
    }
  }, [text, voiceOption, autoPlay]);

  // Handle button click
  const handleButtonClick = () => {
    // Retry on error
    if (error) {
      setError(null);
      fetchAndPlayAudio();
      return;
    }

    // First play - fetch audio
    if (!audioRef.current || !audioUrl) {
      fetchAndPlayAudio();
      return;
    }

    // Toggle play/pause
    if (isPlaying) {
      audioRef.current.pause();
    } else {
      audioRef.current.play().catch((err) => {
        console.error('Playback error:', err);
        setError('Failed to play audio');
      });
    }
  };

  // Auto-play effect
  useEffect(() => {
    if (autoPlay && text && !audioUrl) {
      fetchAndPlayAudio();
    }
  }, [autoPlay, text, audioUrl, fetchAndPlayAudio]);

  // Cleanup effect
  useEffect(() => {
    return () => {
      // Cleanup audio URL
      if (audioUrl) {
        URL.revokeObjectURL(audioUrl);
      }
      // Stop and cleanup audio element
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
      }
    };
  }, [audioUrl]);

  // Get button classes based on state
  const getButtonClasses = () => {
    const baseClasses = `relative ${sizeClasses[size]} rounded-full flex items-center justify-center transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2`;

    // Loading state
    if (isLoading) {
      return `${baseClasses} bg-blue-500 text-white cursor-wait`;
    }

    // Error state
    if (error) {
      return `${baseClasses} bg-red-100 text-red-600 hover:bg-red-200 focus:ring-red-500 border-2 border-red-300`;
    }

    // Playing state
    if (isPlaying) {
      return `${baseClasses} bg-green-500 text-white hover:bg-green-600 focus:ring-green-500 shadow-lg`;
    }

    // Paused state
    if (isPaused) {
      return `${baseClasses} bg-yellow-500 text-white hover:bg-yellow-600 focus:ring-yellow-500 shadow-lg`;
    }

    // Idle state
    return `${baseClasses} bg-gray-100 text-gray-700 hover:bg-gray-200 focus:ring-primary-500 shadow-md hover:shadow-lg`;
  };

  // Get tooltip text
  const getTooltipText = () => {
    if (isLoading) return 'Generating audio...';
    if (error) return 'Click to retry';
    if (isPlaying) return 'Click to pause';
    if (isPaused) return 'Click to resume';
    return 'Listen to response';
  };

  // Get aria label
  const getAriaLabel = () => {
    if (isLoading) return 'Generating audio';
    if (error) return 'Error occurred, click to retry';
    if (isPlaying) return 'Playing audio, click to pause';
    if (isPaused) return 'Audio paused, click to resume';
    return 'Play audio';
  };

  const iconSize = iconSizes[size];

  return (
    <div className="relative inline-flex flex-col items-center gap-2">
      {/* Main Button */}
      <button
        onClick={handleButtonClick}
        disabled={isLoading}
        className={getButtonClasses()}
        aria-label={getAriaLabel()}
        title={getTooltipText()}
      >
        {/* Animated sound waves (playing only) */}
        {isPlaying && (
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <span className="absolute w-full h-full rounded-full border-2 border-white animate-ping opacity-50" />
            <span className="absolute w-3/4 h-3/4 rounded-full border-2 border-white animate-pulse opacity-75" />
          </div>
        )}

        {/* Icon - changes based on state */}
        {isLoading ? (
          // Spinning loader icon
          <svg
            className={`${iconSize} animate-spin`}
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
        ) : isPaused ? (
          // Speaker icon (muted/paused)
          <svg
            className={iconSize}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z"
            />
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M17 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2"
            />
          </svg>
        ) : (
          // Speaker icon (with volume)
          <svg
            className={iconSize}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z"
            />
          </svg>
        )}
      </button>

      {/* Status Text */}
      {isLoading && (
        <span className="text-xs text-blue-600 font-medium">Loading...</span>
      )}
      {isPlaying && (
        <span className="text-xs text-green-600 font-medium">Playing</span>
      )}
      {isPaused && (
        <span className="text-xs text-yellow-600 font-medium">Paused</span>
      )}

      {/* Error Display */}
      {error && (
        <div className="absolute top-full mt-3 w-64 z-10 animate-slideUp">
          <ErrorAlert
            message={error}
            onClose={() => setError(null)}
          />
        </div>
      )}
    </div>
  );
}

