# One image for Hugging Face Spaces: React build + FastAPI + local models baked in.
FROM node:20-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
ENV PIP_NO_CACHE_DIR=1 PYTHONUNBUFFERED=1 HF_HOME=/app/.hf TOKENIZERS_PARALLELISM=false
RUN useradd -m -u 1000 user
WORKDIR /app
COPY requirements.txt .
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu && pip install -r requirements.txt
COPY config.yaml .
COPY promo_finder promo_finder
COPY server server
COPY --from=web /web/dist web/dist
# Download the small local models at build time so the app never cold-downloads them.
RUN python -c "from promo_finder.signals import embedder, _emotion_model; \
embedder('BAAI/bge-small-en-v1.5'); _emotion_model('j-hartmann/emotion-english-distilroberta-base')"
RUN mkdir -p outputs data .cache && chown -R user /app
USER user
EXPOSE 7860
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "7860"]
