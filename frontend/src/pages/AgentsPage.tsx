import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { agents, documents } from '../services/api';
import type { Agent, Document } from '../types/api';
import LoadingSpinner from '../components/LoadingSpinner';
import ErrorAlert from '../components/ErrorAlert';

export default function AgentsPage() {
  const navigate = useNavigate();
  const [agentsList, setAgentsList] = useState<Agent[]>([]);
  const [documentsList, setDocumentsList] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Create Agent Form State
  const [formName, setFormName] = useState('');
  const [formAiModel, setFormAiModel] = useState<'gpt-4' | 'gpt-3.5-turbo'>('gpt-4');
  const [formDocumentIds, setFormDocumentIds] = useState<number[]>([]);
  const [creating, setCreating] = useState(false);
  const [documentSearchTerm, setDocumentSearchTerm] = useState('');

  // Edit Modal State
  const [editingAgent, setEditingAgent] = useState<Agent & { document_ids?: number[] } | null>(null);
  const [editName, setEditName] = useState('');
  const [editAiModel, setEditAiModel] = useState<'gpt-4' | 'gpt-3.5-turbo'>('gpt-4');
  const [editDocumentIds, setEditDocumentIds] = useState<number[]>([]);
  const [updating, setUpdating] = useState(false);
  const [editSearchTerm, setEditSearchTerm] = useState('');

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [agentsData, documentsData] = await Promise.all([
        agents.getAll(),
        documents.getAll(),
      ]);
      setAgentsList(agentsData);
      setDocumentsList(documentsData);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load data');
    } finally {
      setLoading(false);
    }
  };

  const handleCreateAgent = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formName.trim()) {
      setError('Agent name is required');
      return;
    }

    if (formDocumentIds.length === 0) {
      setError('Please select at least one document');
      return;
    }

    try {
      setCreating(true);
      setError(null);
      await agents.create(formName.trim(), formAiModel, formDocumentIds);
      setSuccessMessage('Agent created successfully!');
      setFormName('');
      setFormDocumentIds([]);
      setDocumentSearchTerm('');
      await fetchData();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create agent');
    } finally {
      setCreating(false);
    }
  };

  const handleToggleDocument = (docId: number, isChecked: boolean) => {
    if (isChecked) {
      setFormDocumentIds([...formDocumentIds, docId]);
    } else {
      setFormDocumentIds(formDocumentIds.filter((id) => id !== docId));
    }
  };

  const handleEditToggle = (docId: number, isChecked: boolean) => {
    if (isChecked) {
      setEditDocumentIds([...editDocumentIds, docId]);
    } else {
      setEditDocumentIds(editDocumentIds.filter((id) => id !== docId));
    }
  };

  const openEditModal = async (agentId: number) => {
    try {
      const agentData = await agents.get(agentId);
      setEditingAgent(agentData);
      setEditName(agentData.name);
      setEditAiModel(agentData.ai_model as 'gpt-4' | 'gpt-3.5-turbo');
      setEditDocumentIds(agentData.document_ids || []);
      setEditSearchTerm('');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load agent details');
    }
  };

  const handleUpdateAgent = async () => {
    if (!editingAgent) return;

    if (!editName.trim()) {
      setError('Agent name is required');
      return;
    }

    try {
      setUpdating(true);
      setError(null);
      
      // Update name and system prompt (if needed)
      await agents.update(editingAgent.id, {
        name: editName.trim(),
      });

      // Update documents
      if (editDocumentIds.length > 0) {
        await agents.linkDocuments(editingAgent.id, editDocumentIds);
      } else {
        await agents.linkDocuments(editingAgent.id, []);
      }

      setSuccessMessage('Agent updated successfully!');
      setEditingAgent(null);
      await fetchData();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to update agent');
    } finally {
      setUpdating(false);
    }
  };

  const handleDeleteAgent = async (id: number) => {
    if (!window.confirm('Are you sure you want to delete this agent?')) {
      return;
    }

    try {
      await agents.delete(id);
      setSuccessMessage('Agent deleted successfully!');
      await fetchData();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to delete agent');
    }
  };

  const filteredDocuments = documentsList.filter((doc) =>
    doc.original_name.toLowerCase().includes(documentSearchTerm.toLowerCase())
  );

  const filteredEditDocuments = documentsList.filter((doc) =>
    doc.original_name.toLowerCase().includes(editSearchTerm.toLowerCase())
  );

  const processedDocs = documentsList.filter(doc => doc.is_processed);

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center py-12">
        <LoadingSpinner />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 py-8 animate-fadeIn">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Hero Section */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">AI Agents</h1>
          <p className="text-gray-600">
            Create and manage AI agents powered by GPT models. Link documents to give your agents knowledge.
          </p>
        </div>

        {/* Alerts */}
        {error && (
          <div className="mb-6 animate-slideUp">
            <ErrorAlert message={error} onClose={() => setError(null)} />
          </div>
        )}

        {successMessage && (
          <div className="mb-6 bg-green-50 border border-green-200 text-green-800 px-4 py-3 rounded-lg flex items-start gap-3 animate-slideUp">
            <svg className="w-5 h-5 text-green-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            <span className="text-sm flex-1">{successMessage}</span>
            <button
              onClick={() => setSuccessMessage(null)}
              className="text-green-600 hover:text-green-800"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        )}

        {/* Two Column Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Create Agent Form - Left Column */}
          <div className="lg:col-span-1">
            <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6 sticky top-24 animate-slideUp">
              <div className="flex items-center gap-3 mb-6">
                <div className="w-10 h-10 bg-primary-100 rounded-lg flex items-center justify-center">
                  <svg className="w-6 h-6 text-primary-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                  </svg>
                </div>
                <div>
                  <h2 className="text-lg font-bold text-gray-900">Create New Agent</h2>
                  <p className="text-xs text-gray-600">Build your AI assistant</p>
                </div>
              </div>

              <form onSubmit={handleCreateAgent} className="space-y-5">
                {/* Agent Name */}
                <div>
                  <label htmlFor="agent-name" className="block text-sm font-medium text-gray-700 mb-2">
                    Agent Name
                  </label>
                  <input
                    id="agent-name"
                    type="text"
                    value={formName}
                    onChange={(e) => setFormName(e.target.value)}
                    className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors"
                    placeholder="e.g., Research Assistant"
                    required
                  />
                </div>

                {/* AI Model */}
                <div>
                  <label htmlFor="ai-model" className="block text-sm font-medium text-gray-700 mb-2">
                    AI Model
                  </label>
                  <div className="grid grid-cols-2 gap-3">
                    <button
                      type="button"
                      onClick={() => setFormAiModel('gpt-4')}
                      className={`p-3 rounded-lg border-2 text-left transition-all duration-200 ${
                        formAiModel === 'gpt-4'
                          ? 'border-amber-400 bg-amber-50'
                          : 'border-gray-200 hover:border-gray-300'
                      }`}
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-lg">⭐</span>
                        <span className="font-semibold text-sm">GPT-4</span>
                      </div>
                      <p className="text-xs text-gray-600">Most capable</p>
                    </button>
                    <button
                      type="button"
                      onClick={() => setFormAiModel('gpt-3.5-turbo')}
                      className={`p-3 rounded-lg border-2 text-left transition-all duration-200 ${
                        formAiModel === 'gpt-3.5-turbo'
                          ? 'border-blue-400 bg-blue-50'
                          : 'border-gray-200 hover:border-gray-300'
                      }`}
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-lg">⚡</span>
                        <span className="font-semibold text-sm">GPT-3.5</span>
                      </div>
                      <p className="text-xs text-gray-600">Faster</p>
                    </button>
                  </div>
                </div>

                {/* Documents Selection */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Link Documents ({formDocumentIds.length} selected)
                  </label>
                  
                  {processedDocs.length === 0 ? (
                    <div className="p-4 bg-gray-50 border border-gray-200 rounded-lg text-center">
                      <p className="text-sm text-gray-600 mb-3">No processed documents available</p>
                      <button
                        type="button"
                        onClick={() => navigate('/documents')}
                        className="text-sm text-primary-600 hover:text-primary-700 font-medium"
                      >
                        Upload Documents →
                      </button>
                    </div>
                  ) : (
                    <>
                      <input
                        type="text"
                        placeholder="Search documents..."
                        value={documentSearchTerm}
                        onChange={(e) => setDocumentSearchTerm(e.target.value)}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm mb-2 focus:outline-none focus:ring-2 focus:ring-primary-500"
                      />
                      <div className="max-h-48 overflow-y-auto border border-gray-300 rounded-lg p-2 space-y-1">
                        {filteredDocuments.filter(doc => doc.is_processed).map((doc) => (
                          <label key={doc.id} className="flex items-center gap-2 p-2 hover:bg-gray-50 rounded cursor-pointer">
                            <input
                              type="checkbox"
                              checked={formDocumentIds.includes(doc.id)}
                              onChange={(e) => handleToggleDocument(doc.id, e.target.checked)}
                              className="w-4 h-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                            />
                            <div className="flex-1 min-w-0">
                              <span className="text-sm text-gray-900 truncate block">{doc.original_name}</span>
                            </div>
                          </label>
                        ))}
                      </div>
                    </>
                  )}
                </div>

                <button
                  type="submit"
                  disabled={creating || processedDocs.length === 0}
                  className="w-full py-3 px-4 bg-gradient-to-r from-slate-800 to-slate-900 hover:from-slate-700 hover:to-slate-800 text-white font-semibold rounded-lg shadow-md hover:shadow-lg transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-slate-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  {creating ? (
                    <>
                      <svg className="animate-spin h-5 w-5 text-white" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                      </svg>
                      <span>Creating...</span>
                    </>
                  ) : (
                    <>
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                      </svg>
                      <span>Create Agent</span>
                    </>
                  )}
                </button>
              </form>
            </div>
          </div>

          {/* Agent List - Right Column */}
          <div className="lg:col-span-2">
            <div className="flex items-center justify-between mb-6">
              <div>
                <h2 className="text-xl font-bold text-gray-900">Your Agents</h2>
                <p className="text-sm text-gray-600">{agentsList.length} agent{agentsList.length !== 1 ? 's' : ''} created</p>
              </div>
            </div>

            {agentsList.length === 0 ? (
              <div className="bg-white rounded-2xl shadow-sm border-2 border-dashed border-gray-300 p-12 text-center animate-slideUp">
                <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-4">
                  <svg className="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                  </svg>
                </div>
                <h3 className="text-lg font-semibold text-gray-900 mb-2">No agents yet</h3>
                <p className="text-gray-600 mb-4">Create your first AI agent to get started</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {agentsList.map((agent, index) => (
                  <div
                    key={agent.id}
                    className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden hover-lift transition-all duration-200 animate-slideUp"
                    style={{ animationDelay: `${index * 0.05}s` }}
                  >
                    {/* Agent Card Header */}
                    <div className={`p-6 bg-gradient-to-br ${
                      agent.ai_model === 'gpt-4'
                        ? 'from-amber-400 to-amber-500'
                        : 'from-blue-400 to-blue-500'
                    }`}>
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="w-12 h-12 bg-white bg-opacity-20 rounded-lg flex items-center justify-center mb-3">
                            <svg className="w-7 h-7 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                            </svg>
                          </div>
                          <h3 className="text-xl font-bold text-white mb-1">{agent.name}</h3>
                          <span className="inline-flex items-center gap-1 px-2 py-1 bg-white bg-opacity-20 rounded-full text-xs font-medium text-white">
                            {agent.ai_model === 'gpt-4' ? '⭐ GPT-4' : '⚡ GPT-3.5'}
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Agent Card Body */}
                    <div className="p-6">
                      <div className="flex items-center gap-2 text-sm text-gray-600 mb-4">
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                        </svg>
                        <span className="font-medium">{agent.document_count} document{agent.document_count !== 1 ? 's' : ''} linked</span>
                      </div>

                      {/* Action Buttons */}
                      <div className="space-y-2">
                        <button
                          onClick={() => navigate(`/chat?agent=${agent.id}`)}
                          className="w-full px-4 py-3 bg-gradient-to-r from-slate-800 to-slate-900 hover:from-slate-700 hover:to-slate-800 text-white rounded-lg font-semibold shadow-md hover:shadow-lg transition-all duration-200 flex items-center justify-center gap-2"
                        >
                          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                          </svg>
                          Start Chat
                        </button>
                        <div className="grid grid-cols-2 gap-2">
                          <button
                            onClick={() => openEditModal(agent.id)}
                            className="px-3 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors duration-200 text-sm font-medium flex items-center justify-center gap-1"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                            </svg>
                            Edit
                          </button>
                          <button
                            onClick={() => handleDeleteAgent(agent.id)}
                            className="px-3 py-2 bg-red-50 text-red-600 rounded-lg hover:bg-red-100 transition-colors duration-200 text-sm font-medium flex items-center justify-center gap-1"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                            </svg>
                            Delete
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Edit Modal */}
      {editingAgent && (
        <div className="fixed inset-0 bg-black bg-opacity-50 backdrop-blur-sm flex items-center justify-center z-50 p-4 animate-fadeIn">
          <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full max-h-[90vh] overflow-y-auto animate-slideUp">
            <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 rounded-t-2xl">
              <div className="flex items-center justify-between">
                <h2 className="text-xl font-bold text-gray-900">Edit Agent</h2>
                <button
                  onClick={() => setEditingAgent(null)}
                  className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                >
                  <svg className="w-5 h-5 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>

            <div className="p-6 space-y-5">
              <div>
                <label htmlFor="edit-name" className="block text-sm font-medium text-gray-700 mb-2">
                  Agent Name
                </label>
                <input
                  id="edit-name"
                  type="text"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                  required
                />
              </div>

              <div>
                <label htmlFor="edit-model" className="block text-sm font-medium text-gray-700 mb-2">
                  AI Model
                </label>
                <select
                  id="edit-model"
                  value={editAiModel}
                  onChange={(e) => setEditAiModel(e.target.value as 'gpt-4' | 'gpt-3.5-turbo')}
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                  disabled
                >
                  <option value="gpt-4">GPT-4</option>
                  <option value="gpt-3.5-turbo">GPT-3.5 Turbo</option>
                </select>
                <p className="mt-1 text-xs text-gray-500">Model cannot be changed after creation</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Linked Documents ({editDocumentIds.length} selected)
                </label>
                <input
                  type="text"
                  placeholder="Search documents..."
                  value={editSearchTerm}
                  onChange={(e) => setEditSearchTerm(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm mb-2 focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
                <div className="max-h-60 overflow-y-auto border border-gray-300 rounded-lg p-2 space-y-1">
                  {filteredEditDocuments.map((doc) => (
                    <label key={doc.id} className="flex items-center gap-2 p-2 hover:bg-gray-50 rounded cursor-pointer">
                      <input
                        type="checkbox"
                        checked={editDocumentIds.includes(doc.id)}
                        onChange={(e) => handleEditToggle(doc.id, e.target.checked)}
                        className="w-4 h-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                      />
                      <div className="flex-1 min-w-0">
                        <span className="text-sm text-gray-900 truncate block">{doc.original_name}</span>
                        {!doc.is_processed && (
                          <span className="text-xs text-yellow-600">Processing...</span>
                        )}
                      </div>
                    </label>
                  ))}
                </div>
              </div>
            </div>

            <div className="sticky bottom-0 bg-gray-50 px-6 py-4 flex gap-3 rounded-b-2xl border-t border-gray-200">
              <button
                onClick={handleUpdateAgent}
                disabled={updating}
                className="flex-1 px-4 py-3 bg-gradient-to-r from-slate-800 to-slate-900 hover:from-slate-700 hover:to-slate-800 text-white font-semibold rounded-lg shadow-md hover:shadow-lg transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {updating ? (
                  <>
                    <svg className="animate-spin h-5 w-5 text-white" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    <span>Updating...</span>
                  </>
                ) : (
                  'Update Agent'
                )}
              </button>
              <button
                onClick={() => setEditingAgent(null)}
                className="px-4 py-3 bg-gray-200 hover:bg-gray-300 text-gray-700 font-semibold rounded-lg transition-colors duration-200"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
