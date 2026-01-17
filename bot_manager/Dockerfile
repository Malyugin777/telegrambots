FROM python:3.12-slim

# Install system dependencies + deno
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg curl unzip \
    && curl -fsSL https://deno.land/install.sh | sh \
    && rm -rf /var/lib/apt/lists/*

ENV DENO_INSTALL="/root/.deno"
ENV PATH="${DENO_INSTALL}/bin:${PATH}"

WORKDIR /app

COPY bot_manager/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Ensure latest yt-dlp
RUN pip install --upgrade yt-dlp

COPY shared/ ./shared/
COPY bot_manager/ ./bot_manager/

# Startup script that updates yt-dlp before running
COPY bot_manager/start.sh /app/start.sh
RUN chmod +x /app/start.sh

RUN mkdir -p /tmp/downloads

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

CMD ["/app/start.sh"]
