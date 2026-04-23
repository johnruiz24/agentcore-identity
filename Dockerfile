FROM --platform=linux/arm64 python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN DEBIAN_FRONTEND=noninteractive apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements-docker.txt requirements.txt
RUN PIP_DEFAULT_TIMEOUT=120 pip install --no-cache-dir --prefer-binary -r requirements.txt -v

# Copy application code
COPY src/ src/
COPY entrypoint.py .

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run Bedrock AgentCore Identity Service
CMD ["python", "entrypoint.py"]
