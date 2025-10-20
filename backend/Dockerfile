FROM mirror.gcr.io/library/python:3.11-slim

# System deps for pyOpenMS & friends
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libboost-all-dev \
    libxerces-c-dev \
    libexpat1-dev \
    libhdf5-dev \
    libbz2-dev \
    liblzma-dev \
    libglib2.0-0 \
    wget \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

# Keep memory in check (helps avoid OOM/SIGKILL with mzML parsing)
ENV OMP_NUM_THREADS=1 \
    MALLOC_ARENA_MAX=2 \
    PYTHONUNBUFFERED=1

EXPOSE 5000

# Use a single worker with a couple threads; recycle periodically
# (Do NOT preload in this workload.)
CMD ["gunicorn", "web_app:app", \
     "--bind=0.0.0.0:5000", \
     "--workers=1", \
     "--threads=2", \
     "--timeout=0", \
     "--graceful-timeout=60", \
     "--max-requests=200", \
     "--max-requests-jitter=50", \
     "--worker-tmp-dir=/dev/shm"]
