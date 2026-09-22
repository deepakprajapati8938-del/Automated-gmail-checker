FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Gmail token / state / sqlite db live here; mount a volume in production so
# they survive container restarts/redeploys.
VOLUME ["/app/data"]

CMD ["python", "-m", "app.main"]
