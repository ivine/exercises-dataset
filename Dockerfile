FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 mcp \
    && useradd --uid 10001 --gid mcp --no-create-home mcp

COPY data/exercises.json data/exercises.json
COPY mcp_server/server.py mcp_server/server.py

USER mcp
EXPOSE 8000

CMD ["python", "mcp_server/server.py"]
