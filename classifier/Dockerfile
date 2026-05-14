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

RUN python - <<'PY'
from pathlib import Path
from urllib.request import urlopen

import rapidocr

models_dir = Path(rapidocr.__file__).resolve().parent / "models"
models_dir.mkdir(parents=True, exist_ok=True)

downloads = {
    "ch_PP-OCRv4_det_mobile.pth": "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.8.0/torch/PP-OCRv4/det/ch_PP-OCRv4_det_mobile.pth",
    "ch_ptocr_mobile_v2.0_cls_mobile.pth": "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.8.0/torch/PP-OCRv4/cls/ch_ptocr_mobile_v2.0_cls_mobile.pth",
    "ch_PP-OCRv4_rec_mobile.pth": "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.8.0/torch/PP-OCRv4/rec/ch_PP-OCRv4_rec_mobile.pth",
}

for filename, url in downloads.items():
    target = models_dir / filename
    if target.exists():
        continue
    with urlopen(url, timeout=300) as response, target.open("wb") as output:
        output.write(response.read())
PY

COPY app/ /app/

ENTRYPOINT ["python", "/app/classify-to-obsidian.py"]
