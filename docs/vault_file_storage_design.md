# Vault File Storage Design

## Overview
The Vault feature provides users with a secure environment to upload, store, and share files privately. Vault files are strictly isolated from regular files used for AI knowledge base ingestion. This design supports both user-level and team-level sharing, leveraging existing Team and Membership models.

## Key Principles
- **Isolation:** Vault files are stored and managed separately from regular files. No changes are made to the existing File model or endpoints.
- **Security:** Only the file owner, explicitly shared users, or team members (via sharing) can access a vault file.
- **Sharing:** Vault files can be shared with individual users and/or teams.
- **Auditability:** All vault file operations are logged and traceable.

## Data Model
### Project
- `uuid`: UUIDField (unique, indexed)
- `name`, `description`, `owner`
- `members`: ManyToMany to User (direct user access)
- `shared_with_teams`: ManyToMany to Team (team access)
- `team`: ForeignKey to Team (optional, for "owned" team)

### VaultFile
- `id`: Primary key
- `file`: FileField, stored under `vault/<project_uuid or user_uuid>/files/<filename>` (**UUIDs are used for both user and project IDs**)
- `project`: ForeignKey to Project (nullable, uses UUID)
- `uploaded_by`: ForeignKey to User (uses UUID)
- `team`: ForeignKey to Team (nullable)
- `shared_with_users`: ManyToMany to User (file-level overrides/additions)
- `shared_with_teams`: ManyToMany to Team (file-level overrides/additions)
- `created_at`, `updated_at`: Timestamps

### Hybrid Permissions Model
- **Project-level sharing:**
    - Users with access: project `owner`, `members`, users in `team`, users in `shared_with_teams`.
    - All files in a project are accessible to these users/teams by default.
- **File-level overrides:**
    - Each VaultFile can specify additional `shared_with_users` or `shared_with_teams`.
    - Access to a file = (project access) ∪ (file-level shared users/teams).
    - Files not in a project use only their own sharing settings.
- **API/Serializer:**
    - Expose both inherited (project) and direct (file) sharing.
    - Prevent removing inherited permissions at the file level.

## API Endpoints
- **Upload Vault File**: `POST /api/vault/files/`
- **List Vault Files**: `GET /api/vault/files/`
- **Download Vault File**: `GET /api/vault/files/<id>/download/`
- **Share Vault File**: `POST /api/vault/files/<id>/share/`

## Serializer & ViewSet
- Dedicated VaultFileSerializer and VaultFileViewSet.
- No changes to regular FileSerializer or FileViewSet.

## Storage Path Logic
- Always under `vault/<project_id or user_id>/files/<filename>`
- Never mixed with regular files or knowledge base content.

## Migration & Rollout
- Create new VaultFile table and related migrations.
- Add new endpoints and permissions logic.
- No migration or changes to existing File table or endpoints.

## Future Extensions
- Granular permission levels (read/write).
- Expiry or access logging for compliance.

---

**This design ensures that Vault files are fully isolated, secure, and support flexible sharing, without impacting the existing file management system.**
