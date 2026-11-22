import { useState, useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import { agents, chat, voice } from '../services/api';
import LoadingSpinner from '../components/LoadingSpinner';
import ErrorAlert from '../components/ErrorAlert';
import VoiceInput from '../components/VoiceInput';
import VoiceOutput from '../components/VoiceOutput';
import VoiceSettings from '../components/VoiceSettings';
import { useVoiceSettings } from '../hooks/useVoiceSettings';

interface Message {
  id: string;
  role: 'user' | 'bot';
  content: string;
  sources?: Array<{ chunk_id: number; text: string; similarity: number }>;
  timestamp: string;
}

export default function ChatPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const agentId = parseInt(searchParams.get('agent') || '0');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const [agent, setAgent] = useState<{ id: number; name: string } | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedSource, setExpandedSource] = useState<{ messageId: string; sourceIndex: number } | null>(null);
  const [voiceMode, setVoiceMode] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  
  // Voice conversation state
  const [isVoiceConversationActive, setIsVoiceConversationActive] = useState(false);
  const [isAISpeaking, setIsAISpeaking] = useState(false);
  const [currentSpeakingMessageId, setCurrentSpeakingMessageId] = useState<string | null>(null);
  const [currentAudio, setCurrentAudio] = useState<HTMLAudioElement | null>(null);
  
  // Voice settings hook
  const { settings, updateSettings } = useVoiceSettings();

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Fetch agent details
  useEffect(() => {
    if (!agentId || agentId === 0) {
      setError('Invalid agent ID');
      setLoading(false);
      return;
    }

    const fetchAgent = async () => {
      try {
        setLoading(true);
        setError(null);
        const agentData = await agents.get(agentId);
        setAgent({ id: agentData.id, name: agentData.name });
      } catch (err: any) {
        setError(err.response?.data?.detail || 'Failed to load agent');
      } finally {
        setLoading(false);
      }
    };

    fetchAgent();
  }, [agentId]);

  // Add initial greeting message when agent loads
  useEffect(() => {
    if (agent && messages.length === 0) {
      const greetingMessage: Message = {
        id: 'greeting',
        role: 'bot',
        content: `Hello! I'm ${agent.name}. I can help you find information from the documents linked to me. Ask me anything!`,
        timestamp: new Date().toISOString(),
      };
      setMessages([greetingMessage]);
    }
  }, [agent, messages.length]);

  // Automatically enable conversation mode when in voice mode
  useEffect(() => {
    setIsVoiceConversationActive(voiceMode);
  }, [voiceMode]);

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputMessage.trim() || sending || !agentId) {
      return;
    }

    const messageContent = inputMessage.trim();

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: messageContent,
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputMessage('');
    setSending(true);
    setError(null);

    try {
      // Use the stored message content instead of inputMessage which is now cleared
      const response = await chat.send(agentId, messageContent);

      const botMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'bot',
        content: response.answer,
        sources: response.sources,
        timestamp: response.timestamp || new Date().toISOString(),
      };

      setMessages((prev) => [...prev, botMessage]);
    } catch (err: any) {
      // chat.send() now throws Error objects with descriptive messages
      setError(err.message || err.response?.data?.detail || 'Failed to send message');
    } finally {
      setSending(false);
    }
  };

  const handleVoiceTranscript = async (transcribedText: string) => {
    if (!transcribedText.trim() || sending || !agentId) {
      return;
    }

    const messageContent = transcribedText.trim();

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: messageContent,
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setSending(true);
    setError(null);

    try {
      const response = await chat.send(agentId, messageContent);

      const botMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'bot',
        content: response.answer,
        sources: response.sources,
        timestamp: response.timestamp || new Date().toISOString(),
      };

      setMessages((prev) => [...prev, botMessage]);
      
      // AUTO-PLAY in voice conversation mode
      if (voiceMode && isVoiceConversationActive) {
        playBotResponse(botMessage);
      }
    } catch (err: any) {
      setError(err.message || err.response?.data?.detail || 'Failed to send message');
    } finally {
      setSending(false);
    }
  };

  // Play bot response with auto-play in voice mode
  const playBotResponse = async (message: Message) => {
    try {
      setIsAISpeaking(true);
      setCurrentSpeakingMessageId(message.id);
      
      // Generate and play audio
      const audioBlob = await voice.speak(message.content, settings.ttsVoice);
      const audioUrl = URL.createObjectURL(audioBlob);
      const audio = new Audio(audioUrl);
      
      // Store audio reference for interruption
      setCurrentAudio(audio);
      
      audio.onended = () => {
        setIsAISpeaking(false);
        setCurrentSpeakingMessageId(null);
        setCurrentAudio(null);
        URL.revokeObjectURL(audioUrl);
      };
      
      audio.onerror = () => {
        setIsAISpeaking(false);
        setCurrentSpeakingMessageId(null);
        setCurrentAudio(null);
        URL.revokeObjectURL(audioUrl);
      };
      
      await audio.play();
    } catch (error) {
      console.error('Auto-play failed:', error);
      setIsAISpeaking(false);
      setCurrentSpeakingMessageId(null);
      setCurrentAudio(null);
    }
  };

  // Stop AI speaking (for interrupt capability)
  const stopAISpeaking = () => {
    if (currentAudio) {
      currentAudio.pause();
      currentAudio.currentTime = 0;
    }
    setIsAISpeaking(false);
    setCurrentSpeakingMessageId(null);
    setCurrentAudio(null);
  };

  const formatTimestamp = (timestamp: string): string => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  if (loading) {
    return (
      <div className="h-screen flex items-center justify-center bg-gray-50">
        <LoadingSpinner />
      </div>
    );
  }

  if (!agent) {
    return (
      <div className="h-screen flex items-center justify-center bg-gray-50 p-6">
        <div className="text-center">
          <ErrorAlert message="Agent not found" />
          <button
            onClick={() => navigate('/dashboard')}
            className="mt-6 px-6 py-3 bg-slate-800 text-white rounded-lg hover:bg-slate-700 font-medium transition-colors duration-200"
          >
            Back to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-gray-50 animate-fadeIn">
      {/* Header - Fixed at top */}
      <div className="bg-white shadow-sm border-b border-gray-200 px-4 sm:px-6 py-4 flex-shrink-0 z-20">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate('/dashboard')}
              className="p-2 hover:bg-gray-100 rounded-lg transition-colors duration-200 flex items-center gap-2 text-gray-600 hover:text-gray-900"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
              <span className="hidden sm:inline text-sm font-medium">Back</span>
            </button>
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-primary-400 to-primary-600 flex items-center justify-center">
                <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                </svg>
              </div>
              <div>
                <h1 className="text-lg font-bold text-gray-900">{agent.name}</h1>
                <p className="text-xs text-gray-600">AI Assistant</p>
              </div>
            </div>
            <div className="ml-auto flex items-center gap-2">
              <button
                onClick={() => setVoiceMode(!voiceMode)}
                className={`p-2.5 rounded-lg transition-all duration-200 flex items-center gap-2 ${
                  voiceMode
                    ? 'bg-primary-100 text-primary-700 hover:bg-primary-200'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
                title={voiceMode ? 'Switch to text input' : 'Switch to voice input'}
                aria-label={voiceMode ? 'Switch to text input' : 'Switch to voice input'}
              >
                {voiceMode ? (
                  <>
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                        d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                    </svg>
                    <span className="text-sm font-medium hidden sm:inline">Voice</span>
                  </>
                ) : (
                  <>
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                        d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                    </svg>
                    <span className="text-sm font-medium hidden sm:inline">Text</span>
                  </>
                )}
              </button>
              <button
                onClick={() => setShowSettings(true)}
                className="p-2.5 rounded-lg bg-gray-100 text-gray-600 hover:bg-gray-200 transition-all duration-200"
                title="Voice settings"
                aria-label="Voice settings"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} 
                    d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} 
                    d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Error Alert - Fixed below header */}
      {error && (
        <div className="px-4 sm:px-6 py-3 border-b border-red-200 bg-red-50 flex-shrink-0 z-20">
          <div className="max-w-5xl mx-auto">
            <ErrorAlert message={error} onClose={() => setError(null)} />
          </div>
        </div>
      )}

      {/* Voice Conversation Mode Indicator */}
      {voiceMode && isVoiceConversationActive && (
        <div className="fixed top-20 left-1/2 transform -translate-x-1/2 z-50">
          <div className="bg-gradient-to-r from-primary-500 to-primary-600 text-white px-6 py-3 rounded-full shadow-lg flex items-center gap-3">
            {isAISpeaking ? (
              <>
                <div className="flex gap-1">
                  <div className="w-1 h-4 bg-white rounded-full animate-wave" style={{animationDelay: '0ms'}}></div>
                  <div className="w-1 h-4 bg-white rounded-full animate-wave" style={{animationDelay: '150ms'}}></div>
                  <div className="w-1 h-4 bg-white rounded-full animate-wave" style={{animationDelay: '300ms'}}></div>
                </div>
                <span className="font-medium">AI is speaking...</span>
              </>
            ) : sending ? (
              <>
                <svg className="animate-spin h-5 w-5" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"/>
                </svg>
                <span className="font-medium">Thinking...</span>
              </>
            ) : (
              <>
                <div className="w-3 h-3 bg-white rounded-full animate-pulse"></div>
                <span className="font-medium">Ready to listen</span>
              </>
            )}
          </div>
        </div>
      )}

      {/* Messages Area - Scrollable (grows to fill space) */}
      <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-6">
        <div className="max-w-5xl mx-auto space-y-6">
          {messages.length === 0 ? (
            <div className="text-center py-12">
              <div className="w-16 h-16 bg-primary-100 rounded-full flex items-center justify-center mx-auto mb-4">
                <svg className="w-8 h-8 text-primary-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
              </div>
              <p className="text-gray-600">Start a conversation with {agent.name}</p>
            </div>
          ) : (
            messages.map((message) => (
              <div
                key={message.id}
                className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'} animate-slideUp`}
              >
                <div
                  className={`max-w-3xl ${
                    message.role === 'user'
                      ? 'ml-12'
                      : 'mr-12'
                  }`}
                >
                  <div className="flex items-start gap-3">
                    {message.role === 'bot' && (
                      <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary-400 to-primary-600 flex items-center justify-center flex-shrink-0">
                        <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                        </svg>
                      </div>
                    )}
                    <div className="flex-1">
                      <div
                        className={`rounded-2xl px-5 py-4 ${
                          message.role === 'user'
                            ? 'bg-gradient-to-br from-slate-700 to-slate-800 text-white rounded-tr-sm shadow-md'
                            : currentSpeakingMessageId === message.id
                              ? 'bg-primary-50 border-2 border-primary-400 text-gray-900 rounded-tl-sm shadow-md animate-pulse'
                              : 'bg-white border border-gray-200 text-gray-900 rounded-tl-sm shadow-sm'
                        }`}
                      >
                        {message.role === 'user' ? (
                          <div className="whitespace-pre-wrap font-medium text-white">{message.content}</div>
                        ) : (
                          <div className="prose prose-sm max-w-none">
                            <ReactMarkdown 
                              components={{
                                p: ({children}) => <p className="mb-3 last:mb-0 text-gray-800 leading-relaxed">{children}</p>,
                                ul: ({children}) => <ul className="mb-3 ml-4 space-y-1.5 list-disc">{children}</ul>,
                                ol: ({children}) => <ol className="mb-3 ml-4 space-y-1.5 list-decimal">{children}</ol>,
                                li: ({children}) => <li className="text-gray-800">{children}</li>,
                                strong: ({children}) => <strong className="font-semibold text-gray-900">{children}</strong>,
                                h2: ({children}) => <h2 className="text-base font-bold text-gray-900 mt-4 mb-2 first:mt-0">{children}</h2>,
                                h3: ({children}) => <h3 className="text-sm font-bold text-gray-900 mt-3 mb-1.5">{children}</h3>,
                                code: ({children}) => <code className="px-1.5 py-0.5 bg-gray-100 text-gray-800 rounded text-sm">{children}</code>,
                              }}
                            >
                              {message.content}
                            </ReactMarkdown>
                          </div>
                        )}
                        
                        {/* Voice Output for Bot Messages (only show in text mode) */}
                        {message.role === 'bot' && !isVoiceConversationActive && (
                          <div className="flex items-center gap-2 mt-3">
                            <VoiceOutput 
                              text={message.content}
                              voice={settings.ttsVoice}
                              autoPlay={settings.autoPlay}
                              size="sm"
                            />
                            <span className="text-xs text-gray-500">Listen to response</span>
                          </div>
                        )}
                        
                        {/* Show speaking indicator in voice conversation mode */}
                        {message.role === 'bot' && isVoiceConversationActive && currentSpeakingMessageId === message.id && (
                          <div className="flex items-center gap-2 mt-3 text-primary-600">
                            <div className="flex gap-1">
                              <div className="w-1 h-3 bg-primary-600 rounded-full animate-bounce"></div>
                              <div className="w-1 h-3 bg-primary-600 rounded-full animate-bounce" style={{animationDelay: '150ms'}}></div>
                              <div className="w-1 h-3 bg-primary-600 rounded-full animate-bounce" style={{animationDelay: '300ms'}}></div>
                            </div>
                            <span className="text-xs font-medium">Speaking...</span>
                          </div>
                        )}
                        
                        {/* Source Citations */}
                        {message.sources && message.sources.length > 0 && (
                          <div className="mt-4 pt-4 border-t border-gray-200">
                            <p className="text-xs font-semibold text-gray-600 mb-2 flex items-center gap-1.5">
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                              </svg>
                              Sources ({message.sources.length})
                            </p>
                            <div className="flex flex-wrap gap-2">
                              {message.sources.map((source, idx) => (
                                <div key={idx} className="relative">
                                  <button
                                    onClick={() => setExpandedSource(
                                      expandedSource?.messageId === message.id && expandedSource?.sourceIndex === idx
                                        ? null
                                        : { messageId: message.id, sourceIndex: idx }
                                    )}
                                    className="text-xs bg-gray-100 text-gray-700 px-3 py-1.5 rounded-full hover:bg-gray-200 transition-colors cursor-pointer font-medium flex items-center gap-1.5"
                                  >
                                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                                    </svg>
                                    Chunk {source.chunk_id} · {(source.similarity * 100).toFixed(0)}%
                                  </button>
                                  
                                  {/* Source Expansion Tooltip */}
                                  {expandedSource?.messageId === message.id && expandedSource?.sourceIndex === idx && (
                                    <div className="absolute bottom-full left-0 mb-2 w-80 max-w-[calc(100vw-2rem)] bg-white border border-gray-300 rounded-lg shadow-xl p-4 z-10 animate-slideUp">
                                      <div className="flex items-start justify-between mb-2">
                                        <span className="text-xs font-semibold text-gray-900">Source Chunk {source.chunk_id}</span>
                                        <button
                                          onClick={(e) => {
                                            e.stopPropagation();
                                            setExpandedSource(null);
                                          }}
                                          className="p-1 hover:bg-gray-100 rounded"
                                        >
                                          <svg className="w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                          </svg>
                                        </button>
                                      </div>
                                      <p className="text-xs text-gray-700 leading-relaxed max-h-48 overflow-y-auto">
                                        {source.text}
                                      </p>
                                      <div className="mt-2 pt-2 border-t border-gray-200">
                                        <span className="text-xs text-gray-600">
                                          Relevance: {(source.similarity * 100).toFixed(1)}%
                                        </span>
                                      </div>
                                    </div>
                                  )}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                      <div
                        className={`text-xs mt-1.5 ${
                          message.role === 'user' ? 'text-gray-500 text-right' : 'text-gray-500 text-left ml-1'
                        }`}
                      >
                        {formatTimestamp(message.timestamp)}
                      </div>
                    </div>
                    {message.role === 'user' && (
                      <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-slate-600 to-slate-700 flex items-center justify-center flex-shrink-0 shadow-sm">
                        <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                        </svg>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))
          )}

          {/* Typing indicator */}
          {sending && (
            <div className="flex justify-start animate-slideUp">
              <div className="max-w-3xl mr-12">
                <div className="flex items-start gap-3">
                  <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary-400 to-primary-600 flex items-center justify-center flex-shrink-0">
                    <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                    </svg>
                  </div>
                  <div className="bg-white border border-gray-200 rounded-2xl rounded-tl-sm px-5 py-4 shadow-sm">
                    <div className="flex items-center gap-1">
                      <div className="w-2 h-2 bg-gray-400 rounded-full animate-pulse"></div>
                      <div className="w-2 h-2 bg-gray-400 rounded-full animate-pulse" style={{ animationDelay: '0.2s' }}></div>
                      <div className="w-2 h-2 bg-gray-400 rounded-full animate-pulse" style={{ animationDelay: '0.4s' }}></div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input Area - Fixed at bottom */}
      <div className="bg-white border-t border-gray-200 px-4 sm:px-6 py-4 flex-shrink-0 z-20">
        <div className="max-w-5xl mx-auto">
          {voiceMode ? (
            // Voice Input Mode
            <div className="flex flex-col items-center gap-3">
              <div className="flex items-center gap-4">
                <VoiceInput 
                  onTranscript={handleVoiceTranscript}
                  isDisabled={sending}
                  size="lg"
                  language={settings.inputLanguage}
                  onStartRecording={isAISpeaking ? stopAISpeaking : undefined}
                />
              </div>
              <p className="text-xs text-gray-500 text-center">
                {isAISpeaking ? 'Click to interrupt and speak' : 'Click the microphone to ask a question'}
              </p>
            </div>
          ) : (
            // Text Input Mode (existing form)
            <>
              <form onSubmit={handleSendMessage} className="flex gap-3">
                <input
                  type="text"
                  value={inputMessage}
                  onChange={(e) => setInputMessage(e.target.value)}
                  placeholder="Ask me anything about your documents..."
                  disabled={sending}
                  className="flex-1 px-4 py-3 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-gray-900 placeholder:text-gray-500"
                />
                <button
                  type="submit"
                  disabled={sending || !inputMessage.trim()}
                  className="px-6 py-3 bg-gradient-to-r from-slate-800 to-slate-900 hover:from-slate-700 hover:to-slate-800 text-white rounded-xl font-semibold shadow-md hover:shadow-lg transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  {sending ? (
                    <>
                      <svg className="animate-spin h-5 w-5 text-white" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                      </svg>
                      <span className="hidden sm:inline">Sending</span>
                    </>
                  ) : (
                    <>
                      <span className="hidden sm:inline">Send</span>
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                      </svg>
                    </>
                  )}
                </button>
              </form>
              <p className="text-xs text-gray-500 mt-2 text-center">
                {agent.name} can make mistakes. Verify important information.
              </p>
            </>
          )}
        </div>
      </div>

      {/* Voice Settings Modal */}
      {showSettings && (
        <VoiceSettings
          isOpen={showSettings}
          onClose={() => setShowSettings(false)}
          settings={settings}
          onUpdateSettings={updateSettings}
        />
      )}
    </div>
  );
}
