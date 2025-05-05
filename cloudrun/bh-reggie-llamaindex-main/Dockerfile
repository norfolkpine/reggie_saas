# === Build stage ===
FROM python:3.10-slim AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# === Final runtime stage ===
FROM python:3.10-slim

WORKDIR /app

COPY --from=builder /usr/local /usr/local
COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
