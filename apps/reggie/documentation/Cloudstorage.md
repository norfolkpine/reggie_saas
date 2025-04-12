Since you're using Django and structuring agents, knowledge bases, documents, and teams, your Google Cloud Storage (GCS) directory structure should reflect these logical entities. Here’s a scalable and intuitive directory structure suggestion:

---

### ✅ **Recommended GCS Directory Structure**

```
gs://<your-bucket>/
│
├── global/
│   ├── knowledge_base/
│   │   └── <uuid_or_slug>/               # unique_code or slug from KnowledgeBase
│   │       └── file.pdf
│   └── documents/
│       └── <uuid_or_slug>/               # for public global document library
│           └── file.pdf
│
├── users/
│   └── <user_id>/
│       ├── uploads/
│       │   └── file.pdf
│       └── agents/
│           └── <agent_id>/               # maps to Agent.name or ID
│               └── sessions/
│                   └── <session_id>/
│                       └── chat_history.json
│
├── teams/
│   └── <team_id>/
│       ├── projects/
│       │   └── <project_id>/
│       │       └── file.pdf
│       └── shared_docs/
│           └── file.pdf
```

---

### 🔍 How this maps to your models:

- `global/knowledge_base/<unique_code>`: for admin-ingested vector docs.
- `users/<user_id>/uploads/`: individual file uploads not tied to agents.
- `users/<user_id>/agents/<agent_id>/sessions/<session_id>`: per-chat session uploads.
- `teams/<team_id>`: for team-wide projects and shared documents.

---

### 💡 Tips

- Use UUIDs or slugs from models like `KnowledgeBase.unique_code` and `Agent.agent_id`.
- Store metadata (e.g. `Document.id`, `uploaded_by`, visibility) in Firestore or Django DB; keep GCS as dumb blob storage.
- Use GCS lifecycle rules to auto-delete ephemeral uploads.
- Use signed URLs for secure downloads from private paths.

Let me know if you want Django logic for upload paths or a helper function to build these paths.