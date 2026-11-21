#!/usr/bin/env bash
# Deploy AegisLedger (backend + frontend) to Cloud Run with Cloud SQL Postgres. Scales to zero.
# Usage: PROJECT_ID=my-proj REGION=asia-south1 GEMINI_API_KEY=... GROQ_API_KEY=... ./deploy_gcp.sh
set -euo pipefail
: "${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-asia-south1}"
SQL_INSTANCE="${SQL_INSTANCE:-aegis-pg}"
DB_PASS="${DB_PASS:-$(openssl rand -hex 12)}"
VAULT_KEY="${VAULT_KEY:-$(openssl rand -hex 32)}"
MOCK="${MOCK_LLM:-false}"
[ -z "${GEMINI_API_KEY:-}${GROQ_API_KEY:-}" ] && MOCK=true

gcloud config set project "$PROJECT_ID"
gcloud services enable run.googleapis.com sqladmin.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

if ! gcloud sql instances describe "$SQL_INSTANCE" >/dev/null 2>&1; then
  gcloud sql instances create "$SQL_INSTANCE" --database-version=POSTGRES_16 --tier=db-f1-micro --region="$REGION"
  gcloud sql users set-password postgres --instance="$SQL_INSTANCE" --password="$DB_PASS"
  gcloud sql databases create aegis --instance="$SQL_INSTANCE"
fi
CONN="$PROJECT_ID:$REGION:$SQL_INSTANCE"

gcloud run deploy aegis-backend --source . --region "$REGION" --allow-unauthenticated \
  --min-instances=0 --max-instances=2 --memory=1Gi --add-cloudsql-instances "$CONN" \
  --set-env-vars "DATABASE_URL=postgresql+psycopg://postgres:${DB_PASS}@/aegis?host=/cloudsql/${CONN},MOCK_LLM=${MOCK},VAULT_KEY=${VAULT_KEY},GEMINI_API_KEY=${GEMINI_API_KEY:-},GROQ_API_KEY=${GROQ_API_KEY:-},ALLOW_DEMO_TAMPER=true"
API_URL="$(gcloud run services describe aegis-backend --region "$REGION" --format='value(status.url)')"

# Build the frontend with the backend URL baked in (NEXT_PUBLIC_* is compile-time).
cat > /tmp/aegis-cloudbuild.yaml <<YAML
steps:
- name: gcr.io/cloud-builders/docker
  args: [build, --build-arg, NEXT_PUBLIC_API_URL=${API_URL}, -t, gcr.io/${PROJECT_ID}/aegis-frontend, .]
images: [gcr.io/${PROJECT_ID}/aegis-frontend]
YAML
gcloud builds submit frontend --config /tmp/aegis-cloudbuild.yaml
gcloud run deploy aegis-frontend --image "gcr.io/${PROJECT_ID}/aegis-frontend" --region "$REGION" \
  --allow-unauthenticated --min-instances=0 --port 3000
echo "Backend:  $API_URL"
echo "Frontend: $(gcloud run services describe aegis-frontend --region "$REGION" --format='value(status.url)')"
