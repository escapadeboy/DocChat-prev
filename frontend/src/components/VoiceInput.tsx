import { useState, useEffect } from 'react';
import { useVoiceRecording } from '../hooks/useVoiceRecording';
import { voice } from '../services/api';
import ErrorAlert from './ErrorAlert';

interface VoiceInputProps {
  onTranscript: (text: string) => void;
  isDisabled?: boolean;
  size?: 'sm' | 'md' | 'lg';
  language?: string;
  onStartRecording?: () => void;
}

/**
 * VoiceInput component for recording and transcribing audio
 * 
 * Features:
 * - Click to start/stop recording
 * - Visual feedback for recording, processing states
 * - Auto-stop after 60 seconds
 * - Real-time duration display
 * - Error handling with user-friendly messages
 */
export default function VoiceInput({ 
  onTranscript, 
  isDisabled = false, 
  size = 'md',
  language = 'en',
  onStartRecording
}: VoiceInputProps) {
  // Local state
  const [isProcessing, setIsProcessing] = useState(false);
  const [transcriptionError, setTranscriptionError] = useState<string | null>(null);

  // Voice recording hook
  const {
    startRecording,
    stopRecording,
    isRecording,
    audioBlob,
    error: recordingError,
    duration,
    clearAudio,
  } = useVoiceRecording();

  // Size variant classes
  const sizeClasses = {
    sm: 'w-10 h-10 text-sm',
    md: 'w-14 h-14 text-base',
    lg: 'w-16 h-16 text-lg',
  };

  const iconSizes = {
    sm: 'w-5 h-5',
    md: 'w-6 h-6',
    lg: 'w-8 h-8',
  };

  // Format duration as MM:SS
  const formatDuration = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  // Auto-stop recording after 60 seconds
  useEffect(() => {
    if (duration >= 60 && isRecording) {
      stopRecording();
    }
  }, [duration, isRecording, stopRecording]);

  // Handle audio blob - transcribe when available
  useEffect(() => {
    if (!audioBlob) return;

    const transcribeAudio = async () => {
      try {
        setIsProcessing(true);
        setTranscriptionError(null);

        const response = await voice.transcribe(audioBlob, language);
        
        // Pass transcribed text to parent
        onTranscript(response.text);
        
        // Clear audio after successful transcription
        clearAudio();
      } catch (err: any) {
        console.error('Transcription error:', err);
        setTranscriptionError(err.message || 'Failed to transcribe audio');
      } finally {
        setIsProcessing(false);
      }
    };

    transcribeAudio();
  }, [audioBlob, onTranscript, clearAudio]);

  // Handle button click
  const handleButtonClick = () => {
    // Clear errors if retrying
    if (recordingError || transcriptionError) {
      setTranscriptionError(null);
      clearAudio();
      return;
    }

    // Toggle recording
    if (isRecording) {
      stopRecording();
    } else {
      // Call interrupt callback if provided (e.g., to stop AI speaking)
      if (onStartRecording) {
        onStartRecording();
      }
      startRecording();
    }
  };

  // Determine button state classes
  const getButtonClasses = () => {
    const baseClasses = `relative ${sizeClasses[size]} rounded-full flex items-center justify-center transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2`;
    
    // Disabled state
    if (isDisabled || isProcessing) {
      return `${baseClasses} bg-gray-300 text-gray-500 cursor-not-allowed opacity-50`;
    }

    // Error state
    if (recordingError || transcriptionError) {
      return `${baseClasses} bg-red-100 text-red-600 hover:bg-red-200 focus:ring-red-500 border-2 border-red-300`;
    }

    // Recording state
    if (isRecording) {
      return `${baseClasses} bg-red-500 text-white hover:bg-red-600 focus:ring-red-500 shadow-lg`;
    }

    // Idle state
    return `${baseClasses} bg-gray-100 text-gray-700 hover:bg-gray-200 focus:ring-primary-500 shadow-md hover:shadow-lg`;
  };

  // Determine tooltip text
  const getTooltipText = () => {
    if (isDisabled) return 'Voice input disabled';
    if (isProcessing) return 'Processing audio...';
    if (recordingError || transcriptionError) return 'Click to retry';
    if (isRecording) return 'Click to stop recording';
    return 'Click to start recording';
  };

  // Determine aria label
  const getAriaLabel = () => {
    if (isProcessing) return 'Processing audio';
    if (isRecording) return `Recording: ${formatDuration(duration)}`;
    if (recordingError || transcriptionError) return 'Error occurred, click to retry';
    return 'Start voice recording';
  };

  const iconSize = iconSizes[size];
  const displayError = recordingError || transcriptionError;

  return (
    <div className="relative inline-flex flex-col items-center gap-2">
      {/* Main Button */}
      <button
        onClick={handleButtonClick}
        disabled={isDisabled || isProcessing}
        className={getButtonClasses()}
        aria-label={getAriaLabel()}
        title={getTooltipText()}
      >
        {/* Pulsing ring animation (recording only) */}
        {isRecording && (
          <span className="absolute inset-0 rounded-full bg-red-500 animate-ping opacity-75" />
        )}

        {/* Icon - changes based on state */}
        {isProcessing ? (
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
        ) : (
          // Microphone icon
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
              d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"
            />
          </svg>
        )}
      </button>

      {/* Duration Display (recording only) */}
      {isRecording && (
        <span className="text-sm font-mono text-gray-700 font-semibold">
          {formatDuration(duration)}
        </span>
      )}

      {/* Processing Text */}
      {isProcessing && (
        <span className="text-sm text-blue-600 font-medium">Processing...</span>
      )}

      {/* Error Display */}
      {displayError && (
        <div className="absolute top-full mt-3 w-64 z-10 animate-slideUp">
          <ErrorAlert 
            message={displayError} 
            onClose={() => {
              setTranscriptionError(null);
              clearAudio();
            }}
          />
        </div>
      )}
    </div>
  );
}

