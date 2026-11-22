import axios from 'axios';
import type { AxiosInstance } from 'axios';
import type {
  User, LoginResponse, Document, Agent, SupportChatResponse, OrderSummary, SupportTicket,
  FeedbackRequest, LiveKitTokenResponse, SupportMetrics,
} from '../types/api';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

// Create axios instance
const api: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000, // 30 second default timeout (increased for voice processing)
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor to add auth token
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor to handle errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    // Log all API errors for debugging
    console.error('[API] Request failed:', {
      url: error.config?.url,
      method: error.config?.method,
      status: error.response?.status,
      statusText: error.response?.statusText,
      data: error.response?.data,
      message: error.message,
    });
    
    if (error.response?.status === 401) {
      // Clear token and redirect to login
      localStorage.removeItem('access_token');
      if (window.location.pathname !== '/login') {
        console.log('[API] 401 Unauthorized - redirecting to login');
        window.location.href = '/login';
      }
    } else if (error.response?.status === 429) {
      console.warn('[API] Rate limit exceeded (429)');
    } else if (error.code === 'ECONNABORTED') {
      console.error('[API] Request timeout');
    } else if (error.code === 'ERR_NETWORK') {
      console.error('[API] Network error - backend may be unreachable');
    }
    
    return Promise.reject(error);
  }
);

// Auth API functions
export const auth = {
  register: async (phone: string, password: string, name: string): Promise<User> => {
    const response = await api.post('/auth/register', {
      phone_number: phone,
      password,
      name,
    });
    return response.data;
  },

  login: async (phone: string, password: string): Promise<LoginResponse> => {
    const response = await api.post('/auth/login', {
      phone_number: phone,
      password,
    });
    return response.data;
  },

  getMe: async (): Promise<User> => {
    const response = await api.get('/auth/me');
    return response.data;
  },

  logout: (): void => {
    localStorage.removeItem('access_token');
  },
};

// Documents API functions
export const documents = {
  upload: async (file: File): Promise<Document> => {
    const formData = new FormData();
    formData.append('file', file);
    
    const response = await api.post('/documents/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  getAll: async (): Promise<Document[]> => {
    const response = await api.get('/documents/');
    return response.data.documents || [];
  },

  get: async (id: number): Promise<Document & { chunk_count: number }> => {
    const response = await api.get(`/documents/${id}`);
    return response.data;
  },

  delete: async (id: number): Promise<void> => {
    await api.delete(`/documents/${id}`);
  },
};

// Agents API functions
export const agents = {
  create: async (name: string, ai_model: 'gpt-4' | 'gpt-3.5-turbo', document_ids: number[]): Promise<Agent> => {
    const response = await api.post('/agents/', {
      name,
      ai_model,
      document_ids,
    });
    return response.data;
  },

  getAll: async (): Promise<Agent[]> => {
    const response = await api.get('/agents/');
    return response.data || [];
  },

  get: async (id: number): Promise<Agent & { document_ids: number[]; chunk_count: number; system_prompt?: string }> => {
    const response = await api.get(`/agents/${id}`);
    return response.data;
  },

  update: async (id: number, data: { name?: string; system_prompt?: string }): Promise<Agent> => {
    const response = await api.put(`/agents/${id}`, data);
    return response.data;
  },

  delete: async (id: number): Promise<void> => {
    await api.delete(`/agents/${id}`);
  },

  linkDocuments: async (agent_id: number, document_ids: number[]): Promise<{ message: string; document_count: number }> => {
    const response = await api.post(`/agents/${agent_id}/documents`, {
      document_ids,
    });
    return response.data;
  },
};

// Chat API functions
export const chat = {
  send: async (agent_id: number, message: string): Promise<{ answer: string; sources: Array<{ chunk_id: number; text: string; similarity: number }>; timestamp: string }> => {
    try {
      const response = await api.post(`/chat/`, {
        agent_id,
        message,
      });
      return response.data;
    } catch (error: any) {
      // Handle specific error codes
      if (error.response) {
        const status = error.response.status;
        const detail = error.response.data?.detail || 'An error occurred';
        
        switch (status) {
          case 404:
            throw new Error(`Agent not found: ${detail}`);
          case 403:
            throw new Error(`Access denied: ${detail}`);
          case 400:
            throw new Error(`Invalid request: ${detail}`);
          case 500:
            throw new Error(`Server error: ${detail}`);
          default:
            throw new Error(detail);
        }
      }
      // Network or other errors
      throw new Error(error.message || 'Failed to send message');
    }
  },
};

// Voice API functions
export const voice = {
  transcribe: async (audioBlob: Blob, language?: string): Promise<{ text: string; language: string }> => {
    try {
      const formData = new FormData();
      formData.append('file', audioBlob, 'audio.webm');
      if (language) {
        formData.append('language', language);
      }
      
      const response = await api.post('/voice/transcribe', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        timeout: 60000, // 1 minute for transcription
      });
      return response.data;
    } catch (error: any) {
      // Handle specific error codes
      if (error.response) {
        const status = error.response.status;
        const detail = error.response.data?.detail || 'Transcription failed';
        
        switch (status) {
          case 400:
            throw new Error(`Invalid audio: ${detail}`);
          case 413:
            throw new Error('Audio file too large (max 25MB)');
          case 500:
            throw new Error(`Transcription error: ${detail}`);
          default:
            throw new Error(detail);
        }
      }
      // Network or other errors
      throw new Error(error.message || 'Failed to transcribe audio');
    }
  },

  speak: async (text: string, voice?: string): Promise<Blob> => {
    try {
      const response = await api.post('/voice/speak', 
        { text, voice: voice || 'alloy' },
        { 
          responseType: 'blob',
          timeout: 120000, // 2 minutes for TTS (long text can take time)
        }
      );
      return response.data;
    } catch (error: any) {
      // Handle specific error codes
      if (error.response) {
        const status = error.response.status;
        
        switch (status) {
          case 400:
            throw new Error('Text too long (max 4096 characters) or invalid voice');
          case 500:
            throw new Error('Text-to-speech generation failed');
          default:
            throw new Error('Failed to generate speech');
        }
      }
      // Network or other errors
      throw new Error(error.message || 'Failed to generate speech');
    }
  },

  chatSpeak: async (agentId: number, audioBlob: Blob, voice?: string): Promise<{
    answer: string;
    audio_base64?: string;
    sources: Array<{ chunk_id: number; text: string; similarity: number }>;
    timestamp: string;
  }> => {
    try {
      const formData = new FormData();
      formData.append('agent_id', agentId.toString());
      formData.append('audio', audioBlob, 'question.webm');
      if (voice) {
        formData.append('voice', voice);
      }
      
      const response = await api.post('/voice/chat-speak', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        timeout: 120000, // 2 minutes for combined voice chat + TTS
      });
      return response.data;
    } catch (error: any) {
      // Handle specific error codes
      if (error.response) {
        const status = error.response.status;
        const detail = error.response.data?.detail || 'Voice chat failed';
        
        switch (status) {
          case 400:
            throw new Error(`Invalid request: ${detail}`);
          case 403:
            throw new Error(`Access denied: ${detail}`);
          case 404:
            throw new Error(`Agent not found: ${detail}`);
          case 413:
            throw new Error('Audio file too large (max 25MB)');
          case 500:
            throw new Error(`Voice chat error: ${detail}`);
          default:
            throw new Error(detail);
        }
      }
      // Network or other errors
      throw new Error(error.message || 'Failed to process voice chat');
    }
  },
};

const errorMessage = (error: any, fallback: string): string =>
  error.response?.data?.detail || error.message || fallback;

// Customer support API functions
export const support = {
  chat: async (message: string, session_id: number | null): Promise<SupportChatResponse> => {
    try {
      const response = await api.post('/support/chat', { message, session_id }, { timeout: 60000 });
      return response.data;
    } catch (error: any) {
      throw new Error(errorMessage(error, 'The support bot failed to respond'));
    }
  },

  orders: async (): Promise<OrderSummary[]> => {
    const response = await api.get('/support/orders');
    return response.data;
  },

  feedback: async (data: FeedbackRequest): Promise<void> => {
    try {
      await api.post('/support/feedback', data);
    } catch (error: any) {
      throw new Error(errorMessage(error, 'Failed to submit feedback'));
    }
  },

  tickets: async (): Promise<SupportTicket[]> => {
    const response = await api.get('/support/tickets');
    return response.data;
  },

  updateTicket: async (id: number, status: SupportTicket['status']): Promise<void> => {
    await api.patch(`/support/tickets/${id}`, { status });
  },

  metrics: async (): Promise<SupportMetrics> => {
    const response = await api.get('/support/metrics');
    return response.data;
  },

  // Token for a live LiveKit voice call; the backend also dispatches the voice agent into the room
  livekitToken: async (): Promise<LiveKitTokenResponse> => {
    try {
      const response = await api.post('/voice/livekit-token');
      return response.data;
    } catch (error: any) {
      throw new Error(errorMessage(error, 'Could not start the voice call'));
    }
  },
};

export default api;
