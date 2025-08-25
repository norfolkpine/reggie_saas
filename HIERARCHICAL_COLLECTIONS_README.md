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

### Collections Management

#### List Collections
```http
GET /api/collections/
```
Returns root-level collections accessible to the user.

#### Get Collection Details
```http
GET /api/collections/{id}/
```
Returns detailed collection information including files and subcollections.

#### Create Folder
```http
POST /api/collections/create-folder/
```
```json
{
    "name": "New Folder",
    "parent_id": 123,  // Optional
    "description": "Folder description",
    "collection_type": "folder"
}
```

#### Move Collection
```http
POST /api/collections/{id}/move-to/
```
```json
{
    "new_parent_id": 456  // null to move to root
}
```

#### Add Files to Collection
```http
POST /api/collections/{id}/add-files/
```
```json
{
    "file_ids": [1, 2, 3]
}
```

#### Reorder Files
```http
POST /api/collections/{id}/reorder-files/
```
```json
{
    "file_orders": [
        {"file_id": 1, "order": 0},
        {"file_id": 2, "order": 1}
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

### React Component Example

```typescript
import { useState } from 'react';

interface Collection {
  id: number;
  name: string;
  children: Collection[];
  files: File[];
  full_path: string;
}

function CollectionTree({ collections }: { collections: Collection[] }) {
  const renderCollection = (collection: Collection, level: number) => (
    <div key={collection.id} style={{ marginLeft: level * 20 }}>
      <div className="collection-item">
        <span className="folder-icon">📁</span>
        <span className="collection-name">{collection.name}</span>
        <span className="collection-path">({collection.full_path})</span>
      </div>
      
      {/* Render sub-collections */}
      {collection.children.map(child => renderCollection(child, level + 1))}
      
      {/* Render files */}
      {collection.files.map(file => (
        <div key={file.id} style={{ marginLeft: (level + 1) * 20 }}>
          <span className="file-icon">📄</span>
          <span className="file-name">{file.title}</span>
          {file.volume_number && (
            <span className="volume-number">(Vol {file.volume_number})</span>
          )}
        </div>
      ))}
    </div>
  );

  return (
    <div className="collection-tree">
      {collections.map(collection => renderCollection(collection, 0))}
    </div>
  );
}
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

## Testing

Run the test script to verify the system works:

```bash
python test_hierarchical_collections.py
```

## Benefits

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
