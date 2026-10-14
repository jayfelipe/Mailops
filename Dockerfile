FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml ./
COPY mailops/ mailops/

RUN pip install --no-cache-dir .

# api by default; the worker service overrides the command
CMD ["uvicorn", "mailops.api:app", "--host", "0.0.0.0", "--port", "8000"]