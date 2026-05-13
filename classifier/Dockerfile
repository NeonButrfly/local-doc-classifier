FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV TZ=America/Anchorage
ENV PIP_ROOT_USER_ACTION=ignore

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    jq \
    file \
    libmagic1 \
    libgl1 \
    libglib2.0-0 \
    tesseract-ocr \
    poppler-utils \
    libreoffice \
    pandoc \
    fonts-dejavu \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt

RUN python -m pip install --upgrade pip setuptools wheel && \
    python -m pip install --no-cache-dir -r /app/requirements.txt

COPY app/ /app/

ENTRYPOINT ["python", "/app/classify-to-obsidian.py"]
