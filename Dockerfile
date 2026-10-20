FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
# Explicit CPU wheels avoid downloading CUDA dependencies for this small ranker.
RUN pip install torch==2.10.0 --index-url https://download.pytorch.org/whl/cpu
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install ".[postgres]"
COPY artifacts ./artifacts
COPY data/demo-incidents.jsonl ./data/demo-incidents.jsonl
COPY reports/evaluation.json ./reports/evaluation.json
RUN useradd --uid 10001 --create-home appuser && mkdir -p /app/.tracelens && chown -R appuser:appuser /app/.tracelens
USER appuser
ENV TRACELENS_ROOT=/app
EXPOSE 8000
CMD ["python", "-m", "tracelens.cli", "serve", "--host", "0.0.0.0"]
