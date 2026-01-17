FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY admin_panel/backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared code
COPY shared/ /app/shared/

# Copy source code
COPY admin_panel/backend/src/ /app/src/

# Set Python path
ENV PYTHONPATH=/app

# Expose port
EXPOSE 8000

# Run with uvicorn
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
