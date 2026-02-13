FROM python:3.14-slim

WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/
RUN pip install --no-cache-dir .

# App requires: filename argument. Webhook comes from DISCORD_WEBHOOK env var.
CMD ["python", "-m", "discord_rss", "/app/urls.txt"]
