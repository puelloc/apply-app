FROM python:3.12-slim-bookworm

WORKDIR /app

COPY policy.py proxy.py main.py ./

# Non-root, read-only where possible. The proxy only logs to stdout and never writes files.
USER nobody

EXPOSE 3128

CMD ["python3", "main.py"]
