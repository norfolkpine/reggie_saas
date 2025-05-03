# Reggie File Upload Components

A set of React components for handling file uploads and ingestion status in the Reggie application.

## Features

- Drag and drop file upload
- Support for multiple file types (PDF, DOCX, TXT, CSV, JSON)
- Auto-ingestion option with knowledge base selection
- Real-time ingestion status tracking
- Progress indicators
- Error handling
- Team support
- TypeScript support

## Installation

1. Install dependencies:
```bash
npm install
```

2. Make sure you have shadcn/ui components installed in your project.

## Usage

### Basic File Upload

```tsx
import { FileUpload } from './components/FileUpload';

function YourComponent() {
  const handleUploadComplete = (files) => {
    console.log('Uploaded files:', files);
  };

  const handleUploadError = (error) => {
    console.error('Upload error:', error);
  };

  return (
    <FileUpload
      onUploadComplete={handleUploadComplete}
      onUploadError={handleUploadError}
    />
  );
}
```

### File Upload with Auto-Ingestion

```tsx
import { FileUpload } from './components/FileUpload';

function YourComponent() {
  const knowledgeBases = [
    { id: 1, name: 'Main Knowledge Base' },
    { id: 2, name: 'Research Documents' },
  ];

  return (
    <FileUpload
      knowledgeBases={knowledgeBases}
      teamId={123} // Optional: for team-specific uploads
      onUploadComplete={(files) => {
        console.log('Uploaded and ingested files:', files);
      }}
    />
  );
}
```

### File Ingestion Status

```tsx
import { FileIngestionStatus } from './components/FileIngestionStatus';

function YourComponent() {
  return (
    <FileIngestionStatus
      fileId={123}
      onComplete={() => {
        console.log('Ingestion completed!');
      }}
      onError={(error) => {
        console.error('Ingestion failed:', error);
      }}
    />
  );
}
```

## Components

### FileUpload

Props:
- `onUploadComplete?: (files: File[]) => void`
- `onUploadError?: (error: string) => void`
- `knowledgeBases?: Array<{ id: number; name: string }>`
- `teamId?: number`

### FileIngestionStatus

Props:
- `fileId: number`
- `onComplete?: () => void`
- `onError?: (error: string) => void`

## Types

The components use TypeScript types defined in `types/file.ts`:

```typescript
interface File {
  id: number;
  title: string;
  // ... other file properties
}

interface FileUploadResponse {
  message: string;
  documents: File[];
}

interface FileIngestResponse {
  message: string;
  results: {
    success: Array<{ id: number; message: string }>;
    failed: Array<{ id: number; error: string }>;
  };
}
```

## API Integration

The components use the `fileService` to communicate with the backend API. The service handles:

- File uploads
- Status polling
- Ingestion requests
- Error handling

## Styling

The components use Tailwind CSS and shadcn/ui components for styling. Make sure you have the following dependencies:

- tailwindcss
- @radix-ui/react-* components
- class-variance-authority
- clsx
- tailwind-merge

## Error Handling

The components include comprehensive error handling:

- File type validation
- Upload errors
- Ingestion errors
- Network errors

All errors are displayed to the user and can be handled through the provided callback functions. 