import { useState, useEffect } from 'react';
import { Progress } from '@/components/ui/progress';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { fileService } from '../services/fileService';
import type { File } from '../types/file';

interface FileIngestionStatusProps {
  fileId: number;
  onComplete?: () => void;
  onError?: (error: string) => void;
}

const statusColors = {
  pending: 'bg-yellow-500',
  processing: 'bg-blue-500',
  completed: 'bg-green-500',
  failed: 'bg-red-500',
} as const;

export function FileIngestionStatus({ fileId, onComplete, onError }: FileIngestionStatusProps) {
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isPolling = true;

    const pollFileStatus = async () => {
      try {
        const fileData = await fileService.getFileStatus(fileId);
        setFile(fileData);
        setError(null);

        if (fileData.ingestion_status === 'processing' && isPolling) {
          setTimeout(pollFileStatus, 2000);
        } else if (fileData.ingestion_status === 'completed' && onComplete) {
          onComplete();
        } else if (fileData.ingestion_status === 'failed' && onError) {
          onError(fileData.ingestion_error || 'Ingestion failed');
        }
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : 'An error occurred';
        setError(errorMessage);
        if (onError) onError(errorMessage);
      }
    };

    pollFileStatus();
    return () => { isPolling = false; };
  }, [fileId, onComplete, onError]);

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    );
  }

  if (!file) {
    return (
      <Card>
        <CardContent className="p-6">
          <div className="flex items-center justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900" />
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg font-medium">
            {file.title}
          </CardTitle>
          <Badge variant="outline" className={statusColors[file.ingestion_status]}>
            {file.ingestion_status.charAt(0).toUpperCase() + file.ingestion_status.slice(1)}
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span>
              {file.ingestion_status === 'processing' 
                ? `Processing document ${file.processed_docs} of ${file.total_docs}`
                : file.ingestion_status === 'completed'
                ? 'Processing complete'
                : 'Waiting to process'}
            </span>
            <span>{Math.round(file.ingestion_progress)}%</span>
          </div>
          
          <Progress value={file.ingestion_progress} />
          
          {file.ingestion_error && (
            <Alert variant="destructive">
              <AlertDescription>{file.ingestion_error}</AlertDescription>
            </Alert>
          )}
        </div>
      </CardContent>
    </Card>
  );
} 