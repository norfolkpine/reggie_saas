import axios from 'axios';
import type { File, FileUploadResponse, FileIngestResponse, FileUploadOptions } from '../types/file';

class FileService {
  private readonly baseUrl = '/api/v1/files';

  async uploadFiles(files: File[], options: FileUploadOptions = {}): Promise<FileUploadResponse> {
    const formData = new FormData();
    
    // Append files
    files.forEach(file => {
      formData.append('files', file);
    });

    // Append options
    if (options.autoIngest) {
      formData.append('auto_ingest', 'true');
      if (options.knowledgeBaseId) {
        formData.append('knowledge_base', options.knowledgeBaseId.toString());
      }
    }

    if (options.teamId) {
      formData.append('team', options.teamId.toString());
    }

    if (options.isGlobal) {
      formData.append('is_global', 'true');
    }

    if (options.visibility) {
      formData.append('visibility', options.visibility);
    }

    const response = await axios.post<FileUploadResponse>(`${this.baseUrl}/bulk-upload/`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  }

  async getFileStatus(fileId: number): Promise<File> {
    const response = await axios.get<File>(`${this.baseUrl}/${fileId}/`);
    return response.data;
  }

  async ingestFiles(fileIds: number[]): Promise<FileIngestResponse> {
    const response = await axios.post<FileIngestResponse>(`${this.baseUrl}/ingest-selected/`, {
      file_ids: fileIds,
    });
    return response.data;
  }

  async reingestFile(fileId: number): Promise<{ message: string }> {
    const response = await axios.post<{ message: string }>(`${this.baseUrl}/${fileId}/reingest/`);
    return response.data;
  }
}

export const fileService = new FileService(); 