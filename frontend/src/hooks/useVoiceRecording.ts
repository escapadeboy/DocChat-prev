import { useState, useRef, useCallback, useEffect } from 'react';

/**
 * Return type for the useVoiceRecording hook
 */
interface UseVoiceRecordingReturn {
  startRecording: () => Promise<void>;
  stopRecording: () => Promise<void>;
  isRecording: boolean;
  audioBlob: Blob | null;
  error: string | null;
  duration: number;
  clearAudio: () => void;
}

/**
 * Custom hook for recording audio from the microphone using the MediaRecorder API.
 * 
 * Features:
 * - Request microphone permission on first use
 * - Support multiple audio formats (webm, mp4, wav)
 * - Track recording duration
 * - Handle permission errors gracefully
 * - Automatic cleanup on unmount
 * 
 * @returns Voice recording controls and state
 */
export const useVoiceRecording = (): UseVoiceRecordingReturn => {
  // State
  const [isRecording, setIsRecording] = useState<boolean>(false);
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [duration, setDuration] = useState<number>(0);

  // Refs for MediaRecorder and related objects
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const durationIntervalRef = useRef<number | null>(null);

  /**
   * Clear the recorded audio and reset duration
   */
  const clearAudio = useCallback(() => {
    setAudioBlob(null);
    setDuration(0);
    setError(null);
  }, []);

  /**
   * Determine the best supported audio format for the browser
   */
  const getSupportedAudioFormat = useCallback((): string => {
    // Try formats in order of preference
    const formats = ['audio/webm', 'audio/mp4', 'audio/wav'];
    
    for (const format of formats) {
      if (MediaRecorder.isTypeSupported(format)) {
        return format;
      }
    }
    
    // Fallback to empty string (browser will use default)
    return '';
  }, []);

  /**
   * Start recording audio from the microphone
   */
  const startRecording = useCallback(async () => {
    try {
      // Clear any previous error and audio
      setError(null);
      setAudioBlob(null);
      setDuration(0);
      audioChunksRef.current = [];

      // Request microphone permission
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      // Determine supported audio format
      const mimeType = getSupportedAudioFormat();
      
      // Create MediaRecorder instance
      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: mimeType || undefined,
      });
      mediaRecorderRef.current = mediaRecorder;

      // Handle data available event - collect audio chunks
      mediaRecorder.ondataavailable = (event: BlobEvent) => {
        if (event.data && event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      // Handle stop event - create final audio blob
      mediaRecorder.onstop = () => {
        const audioBlob = new Blob(audioChunksRef.current, { 
          type: mimeType || 'audio/webm' 
        });
        setAudioBlob(audioBlob);
        audioChunksRef.current = [];
      };

      // Start recording
      mediaRecorder.start();
      setIsRecording(true);

      // Start duration timer (increment every second)
      durationIntervalRef.current = setInterval(() => {
        setDuration(prev => prev + 1);
      }, 1000);

    } catch (err: any) {
      // Handle various permission and device errors
      let errorMessage = 'Failed to start recording';

      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        errorMessage = 'Microphone permission denied. Please allow microphone access to record audio.';
      } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
        errorMessage = 'No microphone found. Please connect a microphone and try again.';
      } else if (err.name === 'NotSupportedError') {
        errorMessage = 'Your browser does not support audio recording.';
      } else if (err.name === 'NotReadableError' || err.name === 'TrackStartError') {
        errorMessage = 'Microphone is already in use by another application.';
      } else if (err.message) {
        errorMessage = err.message;
      }

      setError(errorMessage);
      setIsRecording(false);
      console.error('Error starting recording:', err);
    }
  }, [getSupportedAudioFormat]);

  /**
   * Stop recording audio
   */
  const stopRecording = useCallback(async () => {
    try {
      // Stop MediaRecorder if it exists and is recording
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();
      }

      // Stop all media stream tracks
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
        streamRef.current = null;
      }

      // Clear duration timer
      if (durationIntervalRef.current) {
        clearInterval(durationIntervalRef.current);
        durationIntervalRef.current = null;
      }

      setIsRecording(false);
    } catch (err: any) {
      setError(err.message || 'Failed to stop recording');
      console.error('Error stopping recording:', err);
    }
  }, []);

  /**
   * Cleanup on unmount
   */
  useEffect(() => {
    return () => {
      // Stop recording if active
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();
      }

      // Stop all media stream tracks
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
      }

      // Clear duration timer
      if (durationIntervalRef.current) {
        clearInterval(durationIntervalRef.current);
      }
    };
  }, []);

  return {
    startRecording,
    stopRecording,
    isRecording,
    audioBlob,
    error,
    duration,
    clearAudio,
  };
};

