# Data Retention Policy

This policy defines how files stored in our platform are retained, soft-deleted, and permanently purged, in accordance with **ISO 27001** and **SOC 2** requirements for secure data lifecycle management.
​
## 2. Scope
- Applies to all customer-uploaded files stored in **Google Cloud Storage (GCS)**.
- Covers frontend (React application), backend APIs, database records, and storage buckets.
​
## 3. Retention & Trash Bin
- When a user deletes a file, the system will:
1. Mark the file as **deleted** in the database (`deleted_at`, `deleted_by`).
2. Move the file into the **Trash** state.
- Files in the Trash remain accessible to the original user for **30 days**.
- After **30 days**, files are **automatically and permanently purged** from both the database and GCS.
​
## 4. Permanent Deletion
- A file may be permanently deleted earlier if:
- A user requests “Delete Permanently” via the UI.
- A customer submits a data subject deletion request (DSR).
- Permanent deletion means:
- The file record is hard-deleted from the database.
- The object is securely deleted from GCS, including all object generations if versioning is enabled.
- Metadata and audit logs remain (who deleted, when, what object).
​
## 5. Audit Logging
- Every deletion event (soft delete, permanent delete, purge) is logged with:
- `file_id`
- `bucket` and `object_name`
- `deleted_by` (user ID or service account)
- `timestamp`
- `action` (`soft_delete`, `purge`, `restore`)
- Logs are immutable and retained for **1 year**.
​
## 6. Security Controls
- Deletion from GCS is performed only by backend services using **service account credentials**; frontend clients cannot delete directly.
- GCS objects are deleted with **generation-match conditions** to prevent race conditions.
- All GCS buckets are encrypted at rest and enforce IAM controls.
​
## 7. Exceptions
- Files subject to **legal hold** or **retention policy** are exempt from deletion until the hold expires.
- Such files are excluded from Trash purge jobs until the hold is lifted.
​
## 8. Verification & Monitoring
- Daily scheduled jobs reconcile DB records vs. GCS buckets to detect and clean up orphaned objects.
- Purge jobs generate logs that are reviewed monthly.
- Compliance team verifies deletion evidence during quarterly audits.
