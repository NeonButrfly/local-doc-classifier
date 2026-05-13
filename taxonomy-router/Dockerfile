FROM python:3.12-slim
WORKDIR /router
COPY requirements.txt /router/requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip setuptools wheel && python -m pip install --no-cache-dir -r /router/requirements.txt
COPY train_taxonomy_router.py /router/train_taxonomy_router.py
COPY predict_taxonomy.py /router/predict_taxonomy.py
ENTRYPOINT ["python", "/router/predict_taxonomy.py"]
