# Vault Files Tool Documentation

## Overview

The `VaultFilesTools` is an agent tool that provides access to vault files stored in the system. It allows agents to list, search, and read content from vault files that the user has access to.

## Features

- **List Vault Files**: Get a list of all vault files accessible to the current user
- **Search Vault Files**: Search vault files by filename or content
- **Get File Details**: Retrieve detailed information about a specific vault file
- **Read File Content**: Download and read the content of vault files
- **Project Filtering**: Filter files by project UUID
- **Folder Support**: Handle both files and folders in the vault
- **Folder Navigation**: Browse folder contents and navigate folder structure
- **Root Folder Access**: Get contents of the root folder (parent_id=0)

## Django Integration

The tool works directly with Django models and doesn't make external API calls. It accesses:

- `VaultFile` model for vault file data
- `Project` model for project information
- Direct file storage access for content reading

## Authentication & Permissions

The tool respects Django's permission system and vault file sharing rules:
- Users can only access files they uploaded
- Files shared with them (user-level or team-level)
- Files in projects they have access to
- Project-level sharing permissions are respected

## Available Methods

### `get_vault_files(project_uuid=None, parent_id=None, limit=50, user_id=None)`

Lists vault files accessible to the current user.

**Parameters:**
- `project_uuid` (optional): Filter files by project UUID
- `parent_id` (optional): Filter files by parent folder ID
- `limit` (int): Maximum number of files to return (default: 50)
- `user_id` (optional): User ID to filter files for (if not provided, returns all accessible files)

**Returns:**
Formatted string containing file information including:
- File ID, name, size, type
- Upload date and project information
- Visual indicators for files (📄) and folders (📁)

**Example:**
```python
# Get all vault files
result = vault_tools.get_vault_files()

# Get files from a specific project
result = vault_tools.get_vault_files(project_uuid="123e4567-e89b-12d3-a456-426614174000")

# Get files from a specific folder
result = vault_tools.get_vault_files(parent_id=123)

# Get files for a specific user
result = vault_tools.get_vault_files(user_id=123)
```

### `get_vault_file_by_id(file_id)`

Gets detailed information about a specific vault file.

**Parameters:**
- `file_id` (int): The ID of the vault file to retrieve

**Returns:**
Formatted string containing detailed file information.

**Example:**
```python
result = vault_tools.get_vault_file_by_id(123)
```

### `get_vault_file_content(file_id, max_chars=20000)`

Downloads and reads the content of a vault file.

**Parameters:**
- `file_id` (int): The ID of the vault file to read
- `max_chars` (int): Maximum number of characters to return (default: 20000)

**Returns:**
String containing the file content, truncated if it exceeds the character limit.

**Example:**
```python
# Read file content
content = vault_tools.get_vault_file_content(123)

# Read with custom character limit
content = vault_tools.get_vault_file_content(123, max_chars=50000)
```

### `search_vault_files(query, project_uuid=None, limit=20, user_id=None)`

Searches vault files by filename or content.

**Parameters:**
- `query` (str): Search query string
- `project_uuid` (optional): Filter search to specific project
- `limit` (int): Maximum number of results to return (default: 20)
- `user_id` (optional): User ID to filter files for (if not provided, searches all accessible files)

**Returns:**
Formatted string containing matching files.

**Example:**
```python
# Search all vault files
results = vault_tools.search_vault_files("contract")

# Search within a specific project
results = vault_tools.search_vault_files("report", project_uuid="123e4567-e89b-12d3-a456-426614174000")

# Search files for a specific user
results = vault_tools.search_vault_files("document", user_id=123)
```

### `get_folder_contents(folder_id, user_id=None, include_subfolders=False)`

Gets the contents of a specific folder (files and subfolders).

**Parameters:**
- `folder_id` (int): The ID of the folder to get contents for
- `user_id` (optional): User ID to filter files for (if not provided, returns all accessible files)
- `include_subfolders` (bool): Whether to include files from subfolders (default: False)

**Returns:**
Formatted string containing folder contents with folders and files separated.

**Example:**
```python
# Get contents of a specific folder
contents = vault_tools.get_folder_contents(123)

# Get contents with subfolders included
contents = vault_tools.get_folder_contents(123, include_subfolders=True)

# Get contents for a specific user
contents = vault_tools.get_folder_contents(123, user_id=456)
```

### `get_root_folder_contents(project_uuid=None, user_id=None, include_subfolders=False)`

Gets the contents of the root folder (files and folders with parent_id=0).

**Parameters:**
- `project_uuid` (optional): Filter files by project UUID
- `user_id` (optional): User ID to filter files for (if not provided, returns all accessible files)
- `include_subfolders` (bool): Whether to include files from subfolders (default: False)

**Returns:**
Formatted string containing root folder contents.

**Example:**
```python
# Get root folder contents
contents = vault_tools.get_root_folder_contents()

# Get root folder contents for a specific project
contents = vault_tools.get_root_folder_contents(project_uuid="123e4567-e89b-12d3-a456-426614174000")

# Get root folder contents with subfolders
contents = vault_tools.get_root_folder_contents(include_subfolders=True)
```

## Error Handling

The tool includes comprehensive error handling for:
- File not found errors
- Permission denied errors
- Invalid file formats
- Database query errors
- File reading errors

All errors are logged and returned as user-friendly error messages.

## Usage in Agents

The `VaultFilesTools` is automatically available to all agents through the `CACHED_TOOLS` list in `agent_builder.py`. Agents can use these tools to:

1. **Browse vault contents**: List files and folders in the vault
2. **Search for specific documents**: Find files by name or content
3. **Read document content**: Access the actual content of vault files
4. **Navigate project structure**: Filter files by project or folder

## Security Considerations

- Users can only access vault files they have permission to view
- File sharing permissions are respected (project-level and file-level)
- Direct database access ensures proper Django permission enforcement
- Binary files are handled appropriately (not displayed as text)
- No external network requests are made

## Integration with File Reader Tools

The vault files tool works alongside the existing `FileReaderTools` for processing file content. When reading vault file content, the system can:

1. Download the file from the vault
2. Use `FileReaderTools` to extract text from various file formats
3. Return the processed content to the agent

This provides a complete solution for accessing and processing vault files within the agent system.
