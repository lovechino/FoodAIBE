# ── Stage 1: Builder ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# System deps cần để build một số package
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git \
    && rm -rf /var/lib/apt/lists/*

# [QUAN TRỌNG] Cài PyTorch CPU-only TRƯỚC (~300MB)
# Không có dòng này, pip sẽ tự tải PyTorch full GPU (~2.5GB) khi cài sentence-transformers
RUN pip install --no-cache-dir \
    torch==2.2.0 \
    --index-url https://download.pytorch.org/whl/cpu

# Cài các thư viện còn lại (sentence-transformers sẽ dùng torch CPU đã cài)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Stage 2: Runtime (không có build tools) ───────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Chỉ copy packages đã install, bỏ build-essential và các dev tools
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy source code + data (data chỉ 10MB)
COPY . .

EXPOSE 8000

CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
