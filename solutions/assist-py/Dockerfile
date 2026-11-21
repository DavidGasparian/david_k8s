FROM python:3.11-slim

LABEL maintainer="gasparyan@lab.local"
LABEL version="1.0"

WORKDIR /app
ENV PORT=5450
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app/ ./app/
EXPOSE ${PORT}

CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}