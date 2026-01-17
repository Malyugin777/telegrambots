FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY bot_net/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared code
COPY shared /app/shared

# Copy bot code
COPY bot_net /app/bot_net

# Set Python path
ENV PYTHONPATH=/app

# Run
CMD ["python", "-m", "bot_net.main"]
