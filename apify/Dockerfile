# Dockerfile for Sarah AI Apify Actor
FROM python:3.10-slim

# Install system dependencies for Docling/OCR
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Install Apify CLI and other Python dependencies
RUN pip install --upgrade pip

# Set working directory
WORKDIR /usr/src/app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Expose port (required by Apify)
EXPOSE 8080

# Set the entry point for the actor
CMD ["python", "-m", "actor"]