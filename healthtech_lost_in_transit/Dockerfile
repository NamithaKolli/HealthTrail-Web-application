FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5000 \
    DATABASE_PATH=/var/data/healthtransit.db \
    UPLOAD_FOLDER=/var/data/uploads \
    COOKIE_SECURE=0

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /var/data/uploads
EXPOSE 5000
CMD ["sh", "-c", "gunicorn --workers 2 --threads 4 --timeout 90 --bind 0.0.0.0:${PORT} app:app"]
