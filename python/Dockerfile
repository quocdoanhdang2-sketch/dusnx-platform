FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml /app/pyproject.toml
COPY src /app/src
RUN pip install --no-cache-dir .
COPY apps /app/apps
ENV PYTHONPATH=/app/src
EXPOSE 8000
CMD ["uvicorn", "apps.ai_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
