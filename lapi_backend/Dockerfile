# Frozen to the base image used by the current OCI deployment.
FROM python:3.12.15-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
WORKDIR /app
COPY requirements.txt requirements-local.txt requirements-models.txt requirements-oracle.txt ./
ARG INSTALL_LOCAL_EMBEDDINGS=true
ARG INSTALL_CLOUD_MODELS=true
ARG INSTALL_ORACLE=false
# Retained for existing build callers; OCI was already in the shared lock.
ARG INSTALL_OCI=false
RUN pip install --no-cache-dir -r requirements.txt && if [ "$INSTALL_LOCAL_EMBEDDINGS" = "true" ]; then pip install --no-cache-dir -r requirements-local.txt -c requirements.txt; fi && if [ "$INSTALL_CLOUD_MODELS" = "true" ]; then pip install --no-cache-dir -r requirements-models.txt -c requirements.txt; fi
RUN if [ "$INSTALL_ORACLE" = "true" ]; then pip install --no-cache-dir -r requirements-oracle.txt -c requirements.txt; fi
COPY lapi_app ./lapi_app
# Chat and extraction require the pinned local reranker; bake it in so the container needs no download at run time.
ARG INSTALL_RERANKER=true
ENV LAPI_RERANK_MODEL_DIR=/opt/lapi-reranker
RUN if [ "$INSTALL_RERANKER" = "true" ]; then python -c "from huggingface_hub import hf_hub_download; from lapi_app.reranker import MODEL_ID, REVISION, verify_assets; [hf_hub_download(repo_id=MODEL_ID, revision=REVISION, filename=f, local_dir='/opt/lapi-reranker', token=False) for f in ('onnx/model.onnx', 'tokenizer.json')]; verify_assets('/opt/lapi-reranker')" && rm -rf /opt/lapi-reranker/.cache; fi
RUN useradd --create-home --uid 10001 lapi && mkdir -p /data && chown lapi:lapi /data /app
USER lapi
ENV LAPI_STORAGE_ROOT=/data PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "lapi_app.main:app", "--host", "0.0.0.0", "--port", "8000"]
