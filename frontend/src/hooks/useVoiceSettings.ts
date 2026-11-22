import { useState } from 'react';

export interface VoiceSettings {
  ttsVoice: 'alloy' | 'echo' | 'fable' | 'onyx' | 'nova' | 'shimmer';
  autoPlay: boolean;
  inputLanguage: string;
}

const VOICE_SETTINGS_KEY = 'docChat_voiceSettings';

const DEFAULT_SETTINGS: VoiceSettings = {
  ttsVoice: 'alloy',
  autoPlay: false,
  inputLanguage: 'en'
};

/**
 * Custom hook for managing voice settings with localStorage persistence
 * 
 * Features:
 * - Load settings from localStorage on mount
 * - Persist changes automatically to localStorage
 * - Type-safe settings object
 * - Graceful fallback if localStorage unavailable
 */
export function useVoiceSettings() {
  const [settings, setSettings] = useState<VoiceSettings>(() => {
    try {
      // Load from localStorage on mount
      const stored = localStorage.getItem(VOICE_SETTINGS_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        // Validate parsed settings have all required fields
        if (parsed.ttsVoice && typeof parsed.autoPlay === 'boolean' && parsed.inputLanguage) {
          return parsed as VoiceSettings;
        }
      }
    } catch (error) {
      console.error('Failed to load voice settings from localStorage:', error);
    }
    return DEFAULT_SETTINGS;
  });

  const updateSettings = (newSettings: Partial<VoiceSettings>) => {
    const updated = { ...settings, ...newSettings };
    setSettings(updated);
    
    try {
      localStorage.setItem(VOICE_SETTINGS_KEY, JSON.stringify(updated));
    } catch (error) {
      console.error('Failed to save voice settings to localStorage:', error);
    }
  };

  return { settings, updateSettings };
}

