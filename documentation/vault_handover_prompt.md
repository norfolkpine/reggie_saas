# Vault File Storage Handover – Developer Prompt

## Overview
This document provides context and guidance for taking over the Vault File Storage implementation. The Vault system enables secure, isolated file storage for users and teams, with hybrid project/file-level sharing, and is fully separated from the knowledge base file system.

---

## Key Concepts
- **VaultFile model:** Stores privileged files, supports both project and file-level sharing.
- **Project model:** Now supports direct user membership (`members`) and team sharing (`shared_with_teams`), in addition to a primary team (`team`).
- **Hybrid Permissions:**
  - Project-level: Owner, members, project.team members, and shared_with_teams all have access to project files by default.
  - File-level: Each file can be shared with additional users/teams. A file’s access = (project access) ∪ (file-level access).
  - Files not in a project use only their own sharing settings.
- **UUIDs:** All user and project references (including storage paths) use UUIDs.
- **No changes to regular File system:** Vault is fully isolated from knowledge base file logic.

---

## Code Summary
- **models.py:**
  - `VaultFile` model with fields for file, project, uploaded_by, team, shared_with_users, shared_with_teams, etc.
  - `Project` model with `members` and `shared_with_teams` ManyToMany fields for hybrid access.
- **serializers.py:**
  - `VaultFileSerializer` exposes both inherited (project) and direct (file) sharing, prevents removing inherited permissions.
  - `ProjectSerializer` exposes members and shared_with_teams.
- **views.py:**
  - `VaultFileViewSet` enforces hybrid access: user can access a file if they have project or file-level access.
  - Regular FileViewSet and FileSerializer are untouched.
- **docs/vault_file_storage_design.md:**
  - Full design and permission model, including future extension ideas.

---

## Next Steps for Developer
1. **Run migrations** to apply model changes.
2. **Test the Vault API endpoints** (`/vault/files/`) for upload, sharing, and access control.
3. **Extend or refactor** as needed for:
   - Granular permissions (read/write)
   - Expiry/access logging
   - UI/UX for inherited vs. direct sharing
4. **See `docs/vault_file_storage_design.md`** for detailed requirements and rationale.

---

**Contact:** See previous commit history or project owner for any clarifications.
