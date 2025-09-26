# GCP Deployment: Common gcloud Commands

This document lists all gcloud commands used in the setup and deployment of the bh-reggie-test stack, including Cloud SQL, service accounts, buckets, and Cloud Run.

---

## 1. **Set Project and Region**
```sh
gcloud config set project "$PROJECT_ID"
```

---

## 2. **Enable Required APIs**
```sh
gcloud services enable artifactregistry.googleapis.com --project "$PROJECT_ID"
gcloud services enable sqladmin.googleapis.com --project "$PROJECT_ID"
```

---

## 3. **Cloud SQL**
### Create Cloud SQL Instance
```sh
gcloud sql instances create "$INSTANCE_NAME" \
  --database-version=$PG_VERSION \
  --tier=$TIER \
  --region=$REGION \
  --storage-type=SSD \
  --storage-size=$STORAGE \
  --availability-type=ZONAL \
  --root-password="$DB_PASS"
```

### Create Database
```sh
gcloud sql databases create "$DB_NAME" --instance="$INSTANCE_NAME"
```

### Create User
```sh
gcloud sql users create "$DB_USER" --instance="$INSTANCE_NAME" --password="$DB_PASS"
```

### List Users
```sh
gcloud sql users list --instance="$INSTANCE_NAME" --project="$PROJECT_ID"
```

### Set User Password
```sh
gcloud sql users set-password "$DB_USER" --instance="$INSTANCE_NAME" --password=reggiepass --project="$PROJECT_ID"
```

### Connect to Database
```sh
gcloud sql connect "$INSTANCE_NAME" --user="$DB_USER" --project="$PROJECT_ID" --database="$DB_NAME"
```

---

## 4. **Enable pgvector Extension (Manual Step)**
```sql
-- In the psql prompt:
CREATE EXTENSION IF NOT EXISTS vector;
```

---

## 5. **Service Accounts**
### Create Service Account
```sh
gcloud iam service-accounts create "$SERVICE_ACCOUNT_NAME" \
  --project="$PROJECT_ID" \
  --display-name="Service Account Description"
```

### Assign IAM Roles
```sh
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$SERVICE_ACCOUNT_EMAIL" \
  --role="roles/ROLE_NAME"
```

### Create Service Account Key
```sh
gcloud iam service-accounts keys create \
  ".gcp/creds/${PROJECT_ID}-SERVICE.json" \
  --iam-account=$SERVICE_ACCOUNT_EMAIL
```

---

## 6. **Buckets**
### Create GCS Bucket
```sh
gsutil mb -p "$PROJECT_ID" -c STANDARD -l "$REGION" "gs://$BUCKET_NAME"
```

---

## 7. **Cloud Run**
### Deploy to Cloud Run
```sh
gcloud run deploy "$SERVICE_NAME" \
  --image="$IMAGE" \
  --region="$REGION" \
  --platform=managed \
  --service-account="$SERVICE_ACCOUNT" \
  --memory=2Gi \
  --timeout=900 \
  --allow-unauthenticated \
  --set-env-vars=GCP_PROJECT="$PROJECT_ID" \
  --project="$PROJECT_ID"
```

---

## 8. **General**
### Delete Cloud SQL Instance
```sh
gcloud sql instances delete "$INSTANCE_NAME" --project="$PROJECT_ID" --quiet
```

---

_Replace variables in ALL CAPS with your actual values or reference your deployment.env file._
