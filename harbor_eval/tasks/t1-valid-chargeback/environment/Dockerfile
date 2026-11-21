FROM python:3.12-slim
WORKDIR /app
# `backend/` is staged next to this Dockerfile by run_harbor.sh (see stage step).
COPY backend /app/backend
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
ENV MOCK_LLM=true DATABASE_URL=sqlite:////app/harbor.db LEDGER_BACKOFF_S=0 PYTHONPATH=/app
