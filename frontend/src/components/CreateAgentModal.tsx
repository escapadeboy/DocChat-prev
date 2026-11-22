import { useState, useEffect, useRef } from 'react';
import { agents, documents } from '../services/api';
import type { Document } from '../types/api';
import LoadingSpinner from './LoadingSpinner';

interface CreateAgentModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

interface UploadingFile {
  file: File;
  progress: number;
  error: string | null;
  uploadedId: number | null;
}

export default function CreateAgentModal({ isOpen, onClose, onSuccess }: CreateAgentModalProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  
  const [documentsList, setDocumentsList] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Form state
  const [formName, setFormName] = useState('');
  const [formAiModel, setFormAiModel] = useState<'gpt-4' | 'gpt-3.5-turbo'>('gpt-4');
  const [formDocumentIds, setFormDocumentIds] = useState<number[]>([]);
  const [creating, setCreating] = useState(false);
  const [documentSearchTerm, setDocumentSearchTerm] = useState('');

  // Upload state
  const [uploadingFiles, setUploadingFiles] = useState<Map<string, UploadingFile>>(new Map());
  const [justUploadedIds, setJustUploadedIds] = useState<number[]>([]);
  const [isDragging, setIsDragging] = useState(false);

  useEffect(() => {
    if (isOpen) {
      fetchDocuments();
      // Reset state when modal opens
      setUploadingFiles(new Map());
      setJustUploadedIds([]);
    }
  }, [isOpen]);

  const fetchDocuments = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await documents.getAll();
      setDocumentsList(data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load documents');
    } finally {
      setLoading(false);
    }
  };

  const validateFile = (file: File): string | null => {
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      return 'Only PDF files are allowed';
    }
    if (file.size > 10 * 1024 * 1024) {
      return 'File size must be less than 10MB';
    }
    return null;
  };

  const handleFileUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return;

    const filesToUpload = Array.from(files);
    const newUploadingFiles = new Map(uploadingFiles);

    // Validate and add files
    for (const file of filesToUpload) {
      const validationError = validateFile(file);
      const fileKey = `${file.name}-${file.size}-${Date.now()}`;
      
      if (validationError) {
        newUploadingFiles.set(fileKey, {
          file,
          progress: 0,
          error: validationError,
          uploadedId: null,
        });
      } else {
        newUploadingFiles.set(fileKey, {
          file,
          progress: 0,
          error: null,
          uploadedId: null,
        });
      }
    }

    setUploadingFiles(newUploadingFiles);

    // Upload valid files
    for (const [fileKey, fileData] of newUploadingFiles.entries()) {
      if (fileData.error === null && fileData.progress === 0) {
        await uploadFile(fileKey, fileData.file);
      }
    }
  };

  const uploadFile = async (fileKey: string, file: File) => {
    try {
      // Update progress to show uploading
      setUploadingFiles(prev => {
        const updated = new Map(prev);
        const fileData = updated.get(fileKey);
        if (fileData) {
          updated.set(fileKey, { ...fileData, progress: 50 });
        }
        return updated;
      });

      const uploadedDoc = await documents.upload(file);

      // Update progress to complete
      setUploadingFiles(prev => {
        const updated = new Map(prev);
        const fileData = updated.get(fileKey);
        if (fileData) {
          updated.set(fileKey, {
            ...fileData,
            progress: 100,
            uploadedId: uploadedDoc.id,
          });
        }
        return updated;
      });

      // Add to just uploaded list and auto-select
      setJustUploadedIds(prev => [...prev, uploadedDoc.id]);
      setFormDocumentIds(prev => [...prev, uploadedDoc.id]);

      // Refresh document list
      await fetchDocuments();
    } catch (err: any) {
      setUploadingFiles(prev => {
        const updated = new Map(prev);
        const fileData = updated.get(fileKey);
        if (fileData) {
          updated.set(fileKey, {
            ...fileData,
            progress: 0,
            error: err.response?.data?.detail || 'Upload failed',
          });
        }
        return updated;
      });
    }
  };

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    handleFileUpload(e.target.files);
    // Reset input so same file can be uploaded again
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    handleFileUpload(e.dataTransfer.files);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const removeUploadingFile = (fileKey: string) => {
    setUploadingFiles(prev => {
      const updated = new Map(prev);
      updated.delete(fileKey);
      return updated;
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formName.trim()) {
      setError('Agent name is required');
      return;
    }

    if (formDocumentIds.length === 0) {
      setError('Please select or upload at least one document');
      return;
    }

    // Check if any uploads are in progress
    const uploading = Array.from(uploadingFiles.values()).some(
      f => f.progress > 0 && f.progress < 100 && !f.error
    );
    if (uploading) {
      setError('Please wait for uploads to complete');
      return;
    }

    try {
      setCreating(true);
      setError(null);
      await agents.create(formName.trim(), formAiModel, formDocumentIds);
      // Reset form
      setFormName('');
      setFormDocumentIds([]);
      setDocumentSearchTerm('');
      setUploadingFiles(new Map());
      setJustUploadedIds([]);
      onSuccess();
      onClose();
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

  const filteredDocuments = documentsList.filter((doc) =>
    doc.original_name.toLowerCase().includes(documentSearchTerm.toLowerCase()) && 
    doc.is_processed &&
    !justUploadedIds.includes(doc.id) // Exclude just uploaded docs
  );

  const justUploadedDocs = documentsList.filter(doc => justUploadedIds.includes(doc.id));
  const processedDocs = documentsList.filter(doc => doc.is_processed);
  const isUploading = Array.from(uploadingFiles.values()).some(
    f => f.progress > 0 && f.progress < 100 && !f.error
  );

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 backdrop-blur-sm flex items-center justify-center z-50 p-4 animate-fadeIn">
      <div className="bg-white rounded-2xl shadow-2xl max-w-lg w-full max-h-[90vh] overflow-y-auto animate-slideUp">
        {/* Header */}
        <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 rounded-t-2xl z-10">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-primary-100 rounded-lg flex items-center justify-center">
                <svg className="w-6 h-6 text-primary-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                </svg>
              </div>
              <div>
                <h2 className="text-xl font-bold text-gray-900">Create New Agent</h2>
                <p className="text-xs text-gray-600">Build your AI assistant</p>
              </div>
            </div>
            <button
              onClick={onClose}
              className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
              disabled={creating || isUploading}
            >
              <svg className="w-5 h-5 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="mx-6 mt-4 bg-red-50 border border-red-200 text-red-800 px-4 py-3 rounded-lg flex items-start gap-3">
            <svg className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span className="text-sm flex-1">{error}</span>
            <button
              onClick={() => setError(null)}
              className="text-red-600 hover:text-red-800"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        )}

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="p-6 space-y-5">
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
              disabled={creating || isUploading}
            />
          </div>

          {/* AI Model */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              AI Model
            </label>
            <div className="grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => setFormAiModel('gpt-4')}
                disabled={creating || isUploading}
                className={`p-3 rounded-lg border-2 text-left transition-all duration-200 ${
                  formAiModel === 'gpt-4'
                    ? 'border-amber-400 bg-amber-50'
                    : 'border-gray-200 hover:border-gray-300'
                } disabled:opacity-50`}
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
                disabled={creating || isUploading}
                className={`p-3 rounded-lg border-2 text-left transition-all duration-200 ${
                  formAiModel === 'gpt-3.5-turbo'
                    ? 'border-blue-400 bg-blue-50'
                    : 'border-gray-200 hover:border-gray-300'
                } disabled:opacity-50`}
              >
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-lg">⚡</span>
                  <span className="font-semibold text-sm">GPT-3.5</span>
                </div>
                <p className="text-xs text-gray-600">Faster</p>
              </button>
            </div>
          </div>

          {/* Upload Documents Section */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Upload New Documents
            </label>
            <div
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onClick={() => fileInputRef.current?.click()}
              className={`border-2 border-dashed rounded-lg p-4 text-center cursor-pointer transition-all duration-200 ${
                isDragging
                  ? 'border-primary-500 bg-primary-50 scale-105'
                  : 'border-gray-300 hover:border-primary-400 hover:bg-gray-50'
              } ${(creating || isUploading) ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf"
                multiple
                onChange={handleFileInput}
                className="hidden"
                disabled={creating || isUploading}
              />
              <div className="w-12 h-12 bg-primary-100 rounded-lg flex items-center justify-center mx-auto mb-2">
                <svg className="w-6 h-6 text-primary-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
              </div>
              <p className="text-sm text-gray-700 font-medium mb-1">
                Drop PDFs here or click to browse
              </p>
              <p className="text-xs text-gray-500">Max 10MB per file</p>
            </div>

            {/* Upload Progress List */}
            {uploadingFiles.size > 0 && (
              <div className="mt-3 space-y-2">
                {Array.from(uploadingFiles.entries()).map(([fileKey, fileData]) => (
                  <div key={fileKey} className="bg-gray-50 border border-gray-200 rounded-lg p-3">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm font-medium text-gray-900 truncate flex-1">
                        {fileData.file.name}
                      </span>
                      <button
                        type="button"
                        onClick={() => removeUploadingFile(fileKey)}
                        className="ml-2 p-1 hover:bg-gray-200 rounded"
                        disabled={fileData.progress > 0 && fileData.progress < 100}
                      >
                        <svg className="w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      </button>
                    </div>
                    
                    {fileData.error ? (
                      <div className="flex items-center gap-2 text-red-600">
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        <span className="text-xs">{fileData.error}</span>
                      </div>
                    ) : fileData.progress === 100 ? (
                      <div className="flex items-center gap-2 text-green-600">
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                        </svg>
                        <span className="text-xs font-medium">Uploaded successfully</span>
                      </div>
                    ) : fileData.progress > 0 ? (
                      <div className="space-y-1">
                        <div className="w-full bg-gray-200 rounded-full h-2">
                          <div
                            className="bg-primary-600 h-2 rounded-full transition-all duration-300"
                            style={{ width: `${fileData.progress}%` }}
                          />
                        </div>
                        <span className="text-xs text-gray-600">Uploading...</span>
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Documents Selection */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Link Documents ({formDocumentIds.length} selected)
            </label>
            
            {loading ? (
              <div className="flex justify-center py-8">
                <LoadingSpinner />
              </div>
            ) : processedDocs.length === 0 && justUploadedDocs.length === 0 ? (
              <div className="p-4 bg-gray-50 border border-gray-200 rounded-lg text-center">
                <p className="text-sm text-gray-600 mb-3">No documents available</p>
                <p className="text-xs text-gray-500">Upload PDFs above or visit Documents page</p>
              </div>
            ) : (
              <>
                <input
                  type="text"
                  placeholder="Search documents..."
                  value={documentSearchTerm}
                  onChange={(e) => setDocumentSearchTerm(e.target.value)}
                  disabled={creating}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm mb-2 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50"
                />
                <div className="max-h-64 overflow-y-auto border border-gray-300 rounded-lg p-2 space-y-2">
                  {/* Just Uploaded Section */}
                  {justUploadedDocs.length > 0 && (
                    <div>
                      <div className="text-xs font-semibold text-primary-600 mb-1 px-2">Just Uploaded</div>
                      {justUploadedDocs.map((doc) => (
                        <label key={doc.id} className="flex items-center gap-2 p-2 bg-primary-50 hover:bg-primary-100 rounded cursor-pointer">
                          <input
                            type="checkbox"
                            checked={formDocumentIds.includes(doc.id)}
                            onChange={(e) => handleToggleDocument(doc.id, e.target.checked)}
                            disabled={creating}
                            className="w-4 h-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500 disabled:opacity-50"
                          />
                          <div className="flex-1 min-w-0">
                            <span className="text-sm text-gray-900 truncate block">{doc.original_name}</span>
                          </div>
                          <svg className="w-4 h-4 text-primary-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                          </svg>
                        </label>
                      ))}
                    </div>
                  )}

                  {/* Existing Documents */}
                  {filteredDocuments.length === 0 && justUploadedDocs.length === 0 ? (
                    <p className="text-sm text-gray-500 text-center py-4">No documents found</p>
                  ) : filteredDocuments.length > 0 ? (
                    <div>
                      {justUploadedDocs.length > 0 && (
                        <div className="text-xs font-semibold text-gray-600 mb-1 px-2 mt-2">Existing Documents</div>
                      )}
                      {filteredDocuments.map((doc) => (
                        <label key={doc.id} className="flex items-center gap-2 p-2 hover:bg-gray-50 rounded cursor-pointer">
                          <input
                            type="checkbox"
                            checked={formDocumentIds.includes(doc.id)}
                            onChange={(e) => handleToggleDocument(doc.id, e.target.checked)}
                            disabled={creating}
                            className="w-4 h-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500 disabled:opacity-50"
                          />
                          <div className="flex-1 min-w-0">
                            <span className="text-sm text-gray-900 truncate block">{doc.original_name}</span>
                          </div>
                        </label>
                      ))}
                    </div>
                  ) : null}
                </div>
              </>
            )}
          </div>

          {/* Footer Buttons */}
          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              disabled={creating || isUploading}
              className="flex-1 px-4 py-3 bg-gray-200 hover:bg-gray-300 text-gray-700 font-semibold rounded-lg transition-colors duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={creating || isUploading || formDocumentIds.length === 0}
              className="flex-1 py-3 px-4 bg-gradient-to-r from-slate-800 to-slate-900 hover:from-slate-700 hover:to-slate-800 text-white font-semibold rounded-lg shadow-md hover:shadow-lg transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-slate-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {creating ? (
                <>
                  <svg className="animate-spin h-5 w-5 text-white" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  <span>Creating...</span>
                </>
              ) : isUploading ? (
                <>
                  <svg className="animate-spin h-5 w-5 text-white" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  <span>Uploading...</span>
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
          </div>
        </form>
      </div>
    </div>
  );
}
