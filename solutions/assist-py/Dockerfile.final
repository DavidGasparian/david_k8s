FROM python:3.11-slim AS builder

WORKDIR /app
COPY requirements.txt . 
RUN pip install --no-cache-dir --prefix=/gasparyan -r requirements.txt

FROM python:3.11-slim AS runner

LABEL maintainer="gasparyan@lab.local"
LABEL version="3.0"

WORKDIR /app
ENV PORT=5450
COPY --from=builder /gasparyan /usr/local
COPY app/ ./app/
EXPOSE ${PORT}

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1
    
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5450"]