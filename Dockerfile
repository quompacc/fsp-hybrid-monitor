FROM python:3.11-slim

# System dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    udev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Create data directory
RUN mkdir -p /app/data

EXPOSE 5000

HEALTHCHECK --interval=5m --timeout=10s --retries=3 \
    CMD curl -f http://localhost:5000/ || exit 1

CMD ["python", "dashboard/app.py"]
