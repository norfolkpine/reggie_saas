import { useState, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { FileIngestionStatus } from './FileIngestionStatus';
import { fileService } from '../services/fileService';
import type { File } from '../types/file';

interface FileUploadProps {
  onUploadComplete?: (files: File[]) => void;
  onUploadError?: (error: string) => void;
  knowledgeBases?: Array<{ id: number; name: string }>;
  teamId?: number;
}

export function FileUpload({ 
  onUploadComplete, 
  onUploadError,
  knowledgeBases = [],
  teamId
}: FileUploadProps) {
  const [files, setFiles] = useState<File[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [autoIngest, setAutoIngest] = useState(false);
  const [selectedKnowledgeBase, setSelectedKnowledgeBase] = useState<string>('');

  const onDrop = useCallback((acceptedFiles: File[]) => {
    setFiles(acceptedFiles);
    setError(null);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
      'text/plain': ['.txt'],
      'text/csv': ['.csv'],
      'application/json': ['.json'],
    },
  });

  const handleUpload = async () => {
    if (files.length === 0) {
      setError('Please select files to upload');
      return;
    }

    if (autoIngest && !selectedKnowledgeBase) {
      setError('Please select a knowledge base for ingestion');
      return;
    }

    setIsUploading(true);
    setError(null);

    try {
      const response = await fileService.uploadFiles(files, {
        autoIngest,
        knowledgeBaseId: autoIngest ? parseInt(selectedKnowledgeBase) : undefined,
        teamId,
      });

      setFiles([]);
      if (onUploadComplete) {
        onUploadComplete(response.documents);
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Upload failed';
      setError(errorMessage);
      if (onUploadError) {
        onUploadError(errorMessage);
      }
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Upload Files</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div
              {...getRootProps()}
              className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors
                ${isDragActive ? 'border-primary bg-primary/5' : 'border-muted-foreground/25 hover:border-primary'}`}
            >
              <input {...getInputProps()} />
              {isDragActive ? (
                <p>Drop the files here ...</p>
              ) : (
                <p>Drag and drop files here, or click to select files</p>
              )}
            </div>

            {files.length > 0 && (
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">
                  {files.length} file(s) selected
                </p>
                <ul className="text-sm">
                  {files.map((file, index) => (
                    <li key={index}>{file.name}</li>
                  ))}
                </ul>
              </div>
            )}

            <div className="flex items-center space-x-2">
              <Switch
                id="auto-ingest"
                checked={autoIngest}
                onCheckedChange={setAutoIngest}
              />
              <Label htmlFor="auto-ingest">Auto-ingest files</Label>
            </div>

            {autoIngest && knowledgeBases.length > 0 && (
              <div className="space-y-2">
                <Label>Select Knowledge Base</Label>
                <Select
                  value={selectedKnowledgeBase}
                  onValueChange={setSelectedKnowledgeBase}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select a knowledge base" />
                  </SelectTrigger>
                  <SelectContent>
                    {knowledgeBases.map((kb) => (
                      <SelectItem key={kb.id} value={kb.id.toString()}>
                        {kb.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            <Button
              onClick={handleUpload}
              disabled={isUploading || files.length === 0}
              className="w-full"
            >
              {isUploading ? 'Uploading...' : 'Upload Files'}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
} 