FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements files first to leverage Docker cache
COPY requirements/base.txt requirements/base.txt
COPY requirements/collector.txt requirements/collector.txt
COPY requirements/consumer.txt requirements/consumer.txt
COPY requirements/query.txt requirements/query.txt
COPY requirements/generator.txt requirements/generator.txt
COPY requirements/test.txt requirements/test.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements/base.txt \
    && pip install --no-cache-dir -r requirements/collector.txt \
    && pip install --no-cache-dir -r requirements/consumer.txt \
    && pip install --no-cache-dir -r requirements/query.txt \
    && pip install --no-cache-dir -r requirements/generator.txt \
    && pip install --no-cache-dir -r requirements/test.txt

# Copy application code
COPY services/collector/ collector/
COPY services/consumer/ consumer/
COPY services/query/ query/
COPY services/generator/ generator/
COPY scripts/ scripts/
COPY .env.example .env

# Install our modules in development mode
RUN pip install -e collector/ \
    && pip install -e consumer/ \
    && pip install -e query/ \
    && pip install -e generator/

# Set Python path
ENV PYTHONPATH=/app

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser 