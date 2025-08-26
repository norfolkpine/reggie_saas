# Hierarchical Collections System

This document explains how to use the new hierarchical collection system for organizing files into folders and subfolders, specifically designed for regulatory document management.

## Overview

The hierarchical collection system allows you to:
- Create nested folder structures (collections within collections)
- Organize regulatory documents by jurisdiction, type, and hierarchy
- Maintain logical relationships between related documents
- Support multi-volume documents with proper ordering
- Provide intuitive folder navigation

## Key Features

### 1. **Hierarchical Structure**
- Collections can have parent-child relationships
- Unlimited nesting levels
- Automatic path generation (e.g., "Australian Regulations/Corporate Tax Act 2001/Volume 1")

### 2. **Collection Types**
- `folder`: General organizational folder
- `regulation`: Regulatory document collection
- `act`: Legislative act collection
- `guideline`: Guideline document collection
- `manual`: Manual or handbook collection

### 3. **Regulatory Metadata**
- `jurisdiction`: Geographic scope (e.g., "Australia", "NSW")
- `regulation_number`: Regulation identifier (e.g., "2001", "No. 123")
- `effective_date`: When the regulation takes effect
- `sort_order`: Ordering within parent collection

### 4. **File Organization**
- Files maintain order within collections
- Support for volume numbers and part numbers
- Automatic ordering by collection, volume, part, and title

## API Endpoints

### Unified Collections API

#### Get Root Contents (Files + Folders)
```http
GET /api/collections/
```
Returns root-level collections and files accessible to the user.

**Response:**
```json
{
  "uuid": null,
  "id": null,
  "name": "Root",
  "description": "Root directory",
  "collection_type": "folder",
  "children": [
    {
      "uuid": "123e4567-e89b-12d3-a456-426614174000",
      "name": "Australian Regulations",
      "collection_type": "folder"
    }
  ],
  "files": [
    {
      "uuid": "987fcdeb-51a2-43d1-b789-123456789abc",
      "title": "Root File.pdf",
      "file_type": "pdf"
    }
  ],
  "full_path": "Root"
}
```

#### Get Collection Contents by UUID
```http
GET /api/collections/?collection_uuid={uuid}
```
Returns contents of a specific collection using UUID parameter.

**Response:**
```json
{
  "uuid": "123e4567-e89b-12d3-a456-426614174000",
  "name": "Australian Regulations",
  "collection_type": "folder",
  "children": [
    {
      "uuid": "456e4567-e89b-12d3-a456-426614174000",
      "name": "Corporate Tax Act 2001",
      "collection_type": "act"
    }
  ],
  "files": [
    {
      "uuid": "789fcdeb-51a2-43d1-b789-123456789abc",
      "title": "Tax Guide.pdf",
      "file_type": "pdf"
    }
  ],
  "full_path": "Australian Regulations"
}
```

#### Get Collection Details
```http
GET /api/collections/{uuid}/
```
Returns detailed collection information including files and subcollections.

#### Create Folder
```http
POST /api/collections/create-folder/
```
```json
{
    "name": "New Folder",
    "parent_uuid": "123e4567-e89b-12d3-a456-426614174000",  // Optional
    "description": "Folder description",
    "collection_type": "folder"
}
```

#### Move Collection
```http
POST /api/collections/{uuid}/move-to/
```
```json
{
    "new_parent_uuid": "456e4567-e89b-12d3-a456-426614174000"  // null to move to root
}
```

#### Add Files to Collection
```http
POST /api/collections/{uuid}/add-files/
```
```json
{
    "file_uuids": ["123e4567-e89b-12d3-a456-426614174000", "987fcdeb-51a2-43d1-b789-123456789abc"]
}
```

#### Reorder Files
```http
POST /api/collections/{uuid}/reorder-files/
```
```json
{
    "file_orders": [
        {"file_uuid": "123e4567-e89b-12d3-a456-426614174000", "order": 0},
        {"file_uuid": "987fcdeb-51a2-43d1-b789-123456789abc", "order": 1}
    ]
}
```

#### Get Collection Tree
```http
GET /api/collections/tree/
```
Returns the complete hierarchical structure.

### File Upload with Collections

#### Upload to Specific Collection
```http
POST /api/files/
Content-Type: multipart/form-data

files: [file1.pdf, file2.pdf]
collection_name: "Corporate Tax Act 2001"
collection_description: "Australian corporate tax legislation"
collection_type: "act"
jurisdiction: "Australia"
regulation_number: "2001"
```

#### Upload to Nested Folder Structure
```http
POST /api/files/
Content-Type: multipart/form-data

files: [volume1.pdf, volume2.pdf, volume3.pdf]
folder_path: "Australian Regulations/Corporate Tax Act 2001"
collection_description: "Australian corporate tax legislation"
collection_type: "act"
jurisdiction: "Australia"
regulation_number: "2001"
volume_numbers: [1, 2, 3]
```

## Usage Examples

### Example 1: Australian Regulations Structure

```python
# Create the main structure
root = Collection.objects.create(
    name="Australian Regulations",
    collection_type="folder"
)

# Create Corporate Tax Act collection
tax_act = Collection.objects.create(
    name="Corporate Tax Act 2001",
    parent=root,
    collection_type="act",
    jurisdiction="Australia",
    regulation_number="2001"
)

# Upload files with volume numbers
files = [volume1_pdf, volume2_pdf, volume3_pdf]
for i, file in enumerate(files):
    File.objects.create(
        file=file,
        title=f"Volume {i+1}",
        collection=tax_act,
        volume_number=i+1,
        collection_order=i
    )
```

### Example 2: AUSTRAC Guidelines

```python
# Create AUSTRAC collection
austrac = Collection.objects.create(
    name="AUSTRAC Guidelines",
    parent=root,
    collection_type="guideline",
    jurisdiction="Australia"
)

# Create sub-collections for specific topics
aml = Collection.objects.create(
    name="AML Guidelines",
    parent=austrac,
    collection_type="guideline"
)

kyc = Collection.objects.create(
    name="KYC Requirements",
    parent=austrac,
    collection_type="guideline"
)
```

## Frontend Integration

### Unified File Manager Implementation

The new unified API allows you to build a Google Drive-style file manager with minimal API calls. Here's a complete implementation:

#### TypeScript Interfaces

```typescript
interface Collection {
  uuid: string;
  id: number;
  name: string;
  description?: string;
  collection_type: 'folder' | 'regulation' | 'act' | 'guideline' | 'manual';
  children: Collection[];
  files: File[];
  full_path: string;
  created_at: string;
}

interface File {
  uuid: string;
  title: string;
  description?: string;
  file_type: string;
  collection?: Collection;
  collection_order: number;
  volume_number?: number;
  part_number?: string;
  created_at: string;
}
```

#### File Manager Class

```typescript
class FileManager {
  private baseUrl = '/api/collections/';

  // Get contents of any location (root or collection)
  async getContents(collectionUuid?: string): Promise<Collection> {
    const params = collectionUuid ? `?collection_uuid=${collectionUuid}` : '';
    const response = await fetch(`${this.baseUrl}${params}`, {
      headers: {
        'Authorization': `Bearer ${this.getAuthToken()}`,
        'Content-Type': 'application/json'
      }
    });
    
    if (!response.ok) {
      throw new Error(`Failed to get contents: ${response.statusText}`);
    }
    
    return response.json();
  }

  // Get root contents
  async getRootContents(): Promise<Collection> {
    return await this.getContents();
  }

  // Get collection contents
  async getCollectionContents(collectionUuid: string): Promise<Collection> {
    return await this.getContents(collectionUuid);
  }

  // Create new folder
  async createFolder(name: string, parentUuid?: string, description?: string): Promise<Collection> {
    const response = await fetch(`${this.baseUrl}create-folder/`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.getAuthToken()}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        name,
        parent_uuid: parentUuid,
        description,
        collection_type: 'folder'
      })
    });

    if (!response.ok) {
      throw new Error(`Failed to create folder: ${response.statusText}`);
    }

    return response.json();
  }

  // Move files to collection
  async moveFilesToCollection(fileUuids: string[], targetCollectionUuid: string): Promise<void> {
    const response = await fetch(`${this.baseUrl}${targetCollectionUuid}/add-files/`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.getAuthToken()}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        file_uuids: fileUuids
      })
    });

    if (!response.ok) {
      throw new Error(`Failed to move files: ${response.statusText}`);
    }
  }

  private getAuthToken(): string {
    // Implement your auth token retrieval logic
    return localStorage.getItem('auth_token') || '';
  }
}
```

#### React Component - Google Drive Style

```typescript
import React, { useState, useEffect } from 'react';

interface FileManagerProps {
  initialCollectionUuid?: string;
}

const FileManager: React.FC<FileManagerProps> = ({ initialCollectionUuid }) => {
  const [currentLocation, setCurrentLocation] = useState<Collection | null>(null);
  const [breadcrumbs, setBreadcrumbs] = useState<Collection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fileManager = new FileManager();

  // Load initial contents
  useEffect(() => {
    loadContents(initialCollectionUuid);
  }, [initialCollectionUuid]);

  const loadContents = async (collectionUuid?: string) => {
    try {
      setLoading(true);
      setError(null);
      
      const contents = await fileManager.getContents(collectionUuid);
      setCurrentLocation(contents);
      
      // Update breadcrumbs
      if (collectionUuid) {
        updateBreadcrumbs(contents);
      } else {
        setBreadcrumbs([]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load contents');
    } finally {
      setLoading(false);
    }
  };

  const updateBreadcrumbs = (collection: Collection) => {
    const ancestors: Collection[] = [];
    let current: Collection | null = collection;
    
    while (current) {
      ancestors.unshift(current);
      // Note: You'll need to implement getParent() or modify the API
      // to get parent collections for breadcrumb navigation
      current = null; // Placeholder
    }
    
    setBreadcrumbs(ancestors);
  };

  const handleFolderClick = (collection: Collection) => {
    loadContents(collection.uuid);
  };

  const handleBreadcrumbClick = (collection: Collection) => {
    loadContents(collection.uuid);
  };

  const handleCreateFolder = async () => {
    const name = prompt('Enter folder name:');
    if (!name) return;

    try {
      const newFolder = await fileManager.createFolder(
        name, 
        currentLocation?.uuid, 
        'New folder'
      );
      
      // Refresh current view
      await loadContents(currentLocation?.uuid);
    } catch (err) {
      alert('Failed to create folder');
    }
  };

  if (loading) return <div className="loading">Loading...</div>;
  if (error) return <div className="error">Error: {error}</div>;
  if (!currentLocation) return <div>No contents found</div>;

  return (
    <div className="file-manager">
      {/* Top Bar */}
      <div className="top-bar">
        <div className="breadcrumbs">
          <span 
            className="breadcrumb-item root"
            onClick={() => loadContents()}
          >
            Root
          </span>
          {breadcrumbs.map((crumb, index) => (
            <React.Fragment key={crumb.uuid}>
              <span className="breadcrumb-separator">/</span>
              <span 
                className="breadcrumb-item"
                onClick={() => handleBreadcrumbClick(crumb)}
              >
                {crumb.name}
              </span>
            </React.Fragment>
          ))}
        </div>
        
        <div className="actions">
          <button onClick={handleCreateFolder} className="btn-create-folder">
            + New Folder
          </button>
        </div>
      </div>

      {/* Current Location Header */}
      <div className="location-header">
        <h1>{currentLocation.name}</h1>
        <p className="location-path">{currentLocation.full_path}</p>
      </div>

      {/* Contents Grid */}
      <div className="contents-grid">
        {/* Folders */}
        {currentLocation.children.length > 0 && (
          <div className="folders-section">
            <h2>Folders</h2>
            <div className="folders-grid">
              {currentLocation.children.map(folder => (
                <div 
                  key={folder.uuid} 
                  className="folder-item"
                  onClick={() => handleFolderClick(folder)}
                >
                  <div className="folder-icon">📁</div>
                  <div className="folder-name">{folder.name}</div>
                  <div className="folder-type">{folder.collection_type}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Files */}
        {currentLocation.files.length > 0 && (
          <div className="files-section">
            <h2>Files</h2>
            <div className="files-grid">
              {currentLocation.files.map(file => (
                <div key={file.uuid} className="file-item">
                  <div className="file-icon">📄</div>
                  <div className="file-name">{file.title}</div>
                  <div className="file-type">{file.file_type}</div>
                  {file.volume_number && (
                    <div className="file-volume">Vol {file.volume_number}</div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Empty State */}
        {currentLocation.children.length === 0 && currentLocation.files.length === 0 && (
          <div className="empty-state">
            <div className="empty-icon">📁</div>
            <h3>This folder is empty</h3>
            <p>Upload files or create subfolders to get started</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default FileManager;
```

#### CSS Styling

```css
.file-manager {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

.top-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 0;
  border-bottom: 1px solid #e1e5e9;
  margin-bottom: 24px;
}

.breadcrumbs {
  display: flex;
  align-items: center;
  gap: 8px;
}

.breadcrumb-item {
  color: #1a73e8;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 4px;
  transition: background-color 0.2s;
}

.breadcrumb-item:hover {
  background-color: #f1f3f4;
}

.breadcrumb-item.root {
  font-weight: 500;
}

.breadcrumb-separator {
  color: #5f6368;
}

.btn-create-folder {
  background-color: #1a73e8;
  color: white;
  border: none;
  padding: 8px 16px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: background-color 0.2s;
}

.btn-create-folder:hover {
  background-color: #1557b0;
}

.location-header {
  margin-bottom: 24px;
}

.location-header h1 {
  margin: 0 0 4px 0;
  font-size: 24px;
  font-weight: 500;
  color: #202124;
}

.location-path {
  margin: 0;
  color: #5f6368;
  font-size: 14px;
}

.contents-grid {
  display: flex;
  flex-direction: column;
  gap: 32px;
}

.folders-section h2,
.files-section h2 {
  margin: 0 0 16px 0;
  font-size: 18px;
  font-weight: 500;
  color: #202124;
}

.folders-grid,
.files-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
}

.folder-item,
.file-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 20px;
  border: 1px solid #e1e5e9;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  text-align: center;
}

.folder-item:hover,
.file-item:hover {
  border-color: #1a73e8;
  box-shadow: 0 2px 8px rgba(26, 115, 232, 0.15);
}

.folder-icon,
.file-icon {
  font-size: 48px;
  margin-bottom: 12px;
}

.folder-name,
.file-name {
  font-weight: 500;
  color: #202124;
  margin-bottom: 4px;
  word-break: break-word;
}

.folder-type,
.file-type {
  font-size: 12px;
  color: #5f6368;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.file-volume {
  font-size: 12px;
  color: #5f6368;
  margin-top: 4px;
}

.empty-state {
  text-align: center;
  padding: 60px 20px;
  color: #5f6368;
}

.empty-state .empty-icon {
  font-size: 64px;
  margin-bottom: 16px;
}

.empty-state h3 {
  margin: 0 0 8px 0;
  font-size: 18px;
  font-weight: 500;
  color: #202124;
}

.empty-state p {
  margin: 0;
  font-size: 14px;
}

.loading {
  text-align: center;
  padding: 60px 20px;
  color: #5f6368;
}

.error {
  text-align: center;
  padding: 60px 20px;
  color: #d93025;
  background-color: #fce8e6;
  border-radius: 8px;
}
```

#### Usage Example

```typescript
// App.tsx
import React from 'react';
import FileManager from './components/FileManager';

function App() {
  return (
    <div className="App">
      <header className="App-header">
        <h1>File Manager</h1>
      </header>
      <main>
        <FileManager />
      </main>
    </div>
  );
}

export default App;
```

### File Upload Component

```typescript
function FileUploadWithCollections() {
  const [folderPath, setFolderPath] = useState('');
  const [collectionType, setCollectionType] = useState('folder');
  const [jurisdiction, setJurisdiction] = useState('');
  const [regulationNumber, setRegulationNumber] = useState('');
  
  const handleUpload = async (files: File[]) => {
    const formData = new FormData();
    
    files.forEach(file => formData.append('files', file));
    
    if (folderPath) {
      formData.append('folder_path', folderPath);
    }
    
    formData.append('collection_type', collectionType);
    formData.append('jurisdiction', jurisdiction);
    formData.append('regulation_number', regulationNumber);
    
    const response = await fetch('/api/files/', {
      method: 'POST',
      body: formData
    });
    
    return response.json();
  };
  
  return (
    <div>
      <input
        type="text"
        placeholder="Folder path (e.g., Australian Regulations/Corporate Tax Act 2001)"
        value={folderPath}
        onChange={(e) => setFolderPath(e.target.value)}
      />
      
      <select value={collectionType} onChange={(e) => setCollectionType(e.target.value)}>
        <option value="folder">Folder</option>
        <option value="regulation">Regulation</option>
        <option value="act">Act</option>
        <option value="guideline">Guideline</option>
      </select>
      
      <input
        type="text"
        placeholder="Jurisdiction (e.g., Australia)"
        value={jurisdiction}
        onChange={(e) => setJurisdiction(e.target.value)}
      />
      
      <input
        type="text"
        placeholder="Regulation Number (e.g., 2001)"
        value={regulationNumber}
        onChange={(e) => setRegulationNumber(e.target.value)}
      />
    </div>
  );
}
```

## Database Schema

### Collection Model
```python
class Collection(BaseModel):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True)
    collection_type = models.CharField(max_length=50, choices=COLLECTION_TYPE_CHOICES)
    jurisdiction = models.CharField(max_length=100, blank=True, null=True)
    regulation_number = models.CharField(max_length=50, blank=True, null=True)
    effective_date = models.DateField(blank=True, null=True)
    sort_order = models.IntegerField(default=0)
    
    class Meta:
        unique_together = ['name', 'parent']
        ordering = ['sort_order', 'name']
```

### File Model (Updated)
```python
class File(models.Model):
    # ... existing fields ...
    collection = models.ForeignKey(Collection, null=True, blank=True)
    volume_number = models.IntegerField(blank=True, null=True)
    part_number = models.CharField(max_length=20, blank=True, null=True)
    collection_order = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['collection', 'collection_order', 'volume_number', 'part_number', 'title']
```

## Migration

To apply the database changes:

```bash
python manage.py migrate reggie
```

## **New Unified API Usage** 🚀

### **Get Root Contents (Files + Folders):**
```bash
curl -X GET "http://localhost:8000/api/collections/" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### **Get Collection Contents by UUID:**
```bash
curl -X GET "http://localhost:8000/api/collections/?collection_uuid=123e4567-e89b-12d3-a456-426614174000" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### **Get Specific Collection:**
```bash
curl -X GET "http://localhost:8000/api/collections/123e4567-e89b-12d3-a456-426614174000/" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### **Frontend Implementation:**
```typescript
// Get contents of any location (root or collection)
const getContents = async (collectionUuid?: string) => {
  const params = collectionUuid ? `?collection_uuid=${collectionUuid}` : '';
  const response = await api.get(`/collections/${params}`);
  return response.data;
};

// Get root contents
const rootContents = await getContents();

// Get collection contents
const folderContents = await getContents('123e4567-e89b-12d3-a456-426614174000');
```

## Testing

Run the test script to verify the system works:

```bash
python test_hierarchical_collections.py
```

## Benefits

### **Unified API Benefits**
1. **Single Endpoint**: One API call gets everything (files + folders) at any level
2. **Consistent Response Format**: Same structure for root and collection views
3. **Minimal API Calls**: No need for multiple requests to build a file manager
4. **UUID-Based**: Collections now use UUIDs like files for consistency
5. **Google Drive Experience**: Build familiar file manager interfaces easily

### **General Benefits**
1. **Logical Organization**: Files are grouped by regulatory context
2. **Easy Navigation**: Intuitive folder structure for users
3. **Metadata Preservation**: Regulatory information is searchable and organized
4. **Scalability**: Supports unlimited nesting and file organization
5. **API Integration**: Full REST API support for programmatic access
6. **Backward Compatibility**: Existing functionality remains unchanged

## Future Enhancements

- Collection templates for common regulatory structures
- Bulk operations on collections
- Collection-level permissions and sharing
- Advanced search within collections
- Collection analytics and usage statistics
