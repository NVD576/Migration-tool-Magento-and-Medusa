FROM python:3.11-slim

WORKDIR /app

# Install system dependencies if needed (e.g. for potential future libraries)
# RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create directory for exports/logs if needed (optional)
RUN mkdir -p exports

EXPOSE 5000

# Set environment to signal we are in Docker
ENV DOCKER_CONTAINER=1

# Run the web application
CMD ["python", "app_web.py"]
