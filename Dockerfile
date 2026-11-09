FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml uv.lock* ./
RUN pip install --no-cache-dir uv && uv pip install --system --no-cache .
COPY hivemind ./hivemind
EXPOSE 8080
CMD ["opentelemetry-instrument", "uvicorn", "hivemind.main:app", "--host", "0.0.0.0", "--port", "8080"]
