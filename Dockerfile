FROM python:3.11-slim

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libglib2.0-0 \
    libgomp1 \
    libgl1 \
    libglib2.0-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install CPU-only PyTorch (smaller than GPU build)
RUN pip install --no-cache-dir \
    torch==2.1.0+cpu \
    --index-url https://download.pytorch.org/whl/cpu || \
    pip install --no-cache-dir torch

# Install all dependencies
RUN pip install --no-cache-dir \
    fastapi==0.111.0 \
    "uvicorn[standard]==0.29.0" \
    pydantic==2.7.1 \
    sqlalchemy==2.0.30 \
    structlog==24.1.0 \
    python-multipart==0.0.9 \
    ultralytics==8.2.18 \
    opencv-python-headless==4.9.0.80 \
    numpy==1.26.4 \
    httpx==0.27.0 \
    python-dotenv==1.0.1

# Pre-download YOLOv8n weights (6MB) — no internet needed at eval time
RUN python3 -c "from ultralytics import YOLO; YOLO('yolov8n.pt')" 2>/dev/null || echo "YOLO weights download skipped"

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
