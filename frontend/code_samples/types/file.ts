export interface File {
  id: number;
  title: string;
  description?: string;
  file_type: 'pdf' | 'docx' | 'txt' | 'csv' | 'json' | 'other';
  gcs_path: string;
  knowledge_base?: number;
  uploaded_by?: number;
  team?: number;
  source?: string;
  visibility: 'public' | 'private';
  is_global: boolean;
  is_ingested: boolean;
  auto_ingest: boolean;
  ingestion_status: 'pending' | 'processing' | 'completed' | 'failed';
  ingestion_error?: string;
  ingestion_started_at?: string;
  ingestion_completed_at?: string;
  ingestion_progress: number;
  processed_docs: number;
  total_docs: number;
  created_at: string;
  updated_at: string;
}

export interface FileUploadResponse {
  message: string;
  documents: File[];
}

export interface FileIngestResponse {
  message: string;
  results: {
    success: Array<{ id: number; message: string }>;
    failed: Array<{ id: number; error: string }>;
  };
}

export interface FileUploadOptions {
  autoIngest?: boolean;
  knowledgeBaseId?: number;
  teamId?: number;
  isGlobal?: boolean;
  visibility?: 'public' | 'private';
} 