# Implementing RBAC in the LlamaIndex Ingestion Script

This guide explains how to add Role-Based Access Control (RBAC) to your ingestion pipeline using metadata fields such as `knowledgebase_id`. The goal is to ensure that every document and chunk in your vector store is tagged with access control information, and that this information is used to enforce permissions during search and retrieval.

## 1. Accepting RBAC Metadata on Ingestion

- Update your ingestion API and request models (`FileIngestRequest`, etc.) to accept RBAC-related fields, such as `knowledgebase_id` (and any other RBAC tags you require).
- Example field:
  ```python
  knowledgebase_id: str = Field(..., description="ID of the knowledgebase for RBAC")
  ```

## 2. Propagating RBAC Metadata to All Chunks

- When splitting documents into chunks, ensure each chunked `Document` gets the correct RBAC metadata.
- Example code snippet:
  ```python
  for doc in batch:
      text_chunks = text_splitter.split_text(doc.text)
      for idx, chunk in enumerate(text_chunks):
          chunk_metadata = dict(doc.metadata) if doc.metadata else {}
          chunk_metadata.update({
              "knowledgebase_id": payload.knowledgebase_id,  # Ensure this comes from the ingestion request
              "chunk_index": idx,
              # Add any other RBAC fields here
          })
          chunked_docs.append(Document(text=chunk, metadata=chunk_metadata))
  ```

## 3. Storing and Querying by RBAC Metadata

- When indexing, the metadata (including `knowledgebase_id`) will be stored in the vector store.
- At query time, filter results by the allowed `knowledgebase_id`(s) for the requesting user.
- You can enforce this in your search logic or as a post-processing step.

## 4. Example: Updating the Ingestion Request Model

Add the RBAC field to your request model:
```python
class FileIngestRequest(BaseModel):
    file_path: str = Field(...)
    vector_table_name: str = Field(...)
    knowledgebase_id: str = Field(..., description="ID of the knowledgebase for RBAC")
    # ... other fields ...
```

## 5. Example: Using RBAC in Search

When handling a search/query request, filter results by `knowledgebase_id`:
```python
allowed_kb_ids = get_allowed_knowledgebase_ids_for_user(user)
results = vector_store.query(
    query_embedding=embedding,
    filter={"knowledgebase_id": {"$in": allowed_kb_ids}}
)
```

## 6. Summary of Steps

1. Accept RBAC fields (e.g., `knowledgebase_id`) in ingestion requests.
2. Propagate RBAC metadata to every chunked document during ingestion.
3. Enforce RBAC at query time by filtering results using the metadata.

---

**Tip:** You can expand this pattern to more complex RBAC needs by adding more metadata fields (such as user roles, group IDs, etc.) and updating your filtering logic accordingly.

---

For further help with code changes, see the main ingestion script or contact the engineering team.
