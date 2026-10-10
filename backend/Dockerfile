FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY alembic.ini .
COPY alembic ./alembic

# Cover artwork is cached under /app/covers (compose volume `covers_data`).
# create it explicitly so the mounted path always exists even before the first
# download (artwork.py also mkdirs at write time).
RUN mkdir -p /app/covers

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
