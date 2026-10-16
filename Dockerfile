# Hugging Face Spaces (SDK docker): o app precisa ouvir na porta 7860.
# NÃO TESTADO: Docker não estava disponível quando este arquivo foi escrito.
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
RUN useradd -m -u 1000 user
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=user api/ api/
COPY --chown=user solver/ solver/
COPY --chown=user pipeline/ pipeline/
COPY --chown=user data/cities/ data/cities/
COPY --chown=user --from=web /web/dist web/dist
USER user
EXPOSE 7860
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "7860"]
