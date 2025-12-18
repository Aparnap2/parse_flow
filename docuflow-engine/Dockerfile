FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    libqpdf-dev \
    zlib1g-dev \
    libjpeg-dev \
    g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-keep-alive", "60"]