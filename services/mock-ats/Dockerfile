FROM python:3.12-slim-bookworm

WORKDIR /app

COPY server.py .
COPY fixtures/ fixtures/

EXPOSE 8000

CMD ["python3", "server.py", "8000"]
