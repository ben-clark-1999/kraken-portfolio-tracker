# Backend-only image. The frontend stays local — it's a dev viewer that
# proxies /api/* to whatever the VITE_API_TARGET env var points at.
FROM python:3.13-slim

WORKDIR /app

# Build deps for any C-extension packages in requirements.txt.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first so Docker can cache the pip layer between
# code edits.
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Application code.
COPY backend /app/backend
COPY supabase /app/supabase

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Railway injects $PORT at runtime. The shell-form CMD lets the
# variable expand; --host 0.0.0.0 is required so the container's
# port is reachable from outside.
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
