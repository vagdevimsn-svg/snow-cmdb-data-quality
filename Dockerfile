FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY cmdb_dq ./cmdb_dq
COPY sample_data ./sample_data
RUN pip install --no-cache-dir . && useradd --create-home --uid 10001 appuser
USER appuser

ENTRYPOINT ["cmdb-dq"]
CMD ["--input", "sample_data/cmdb_export.json"]
