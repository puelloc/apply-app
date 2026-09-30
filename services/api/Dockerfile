FROM python:3.12-slim-bookworm

WORKDIR /app

COPY requirements.txt ./
RUN python3 -m venv /venv && /venv/bin/pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY alembic.ini alembic/ ./

ENV PATH="/venv/bin:${PATH}"

EXPOSE 8000

# Migrate the DB, then serve.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
