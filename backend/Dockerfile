FROM python:3.11-slim

# Install system dependencies required for pyOpenMS
RUN apt-get update && apt-get install -y \
    build-essential \
    libboost-all-dev \
    libxerces-c-dev \
    libexpat1-dev \
    libhdf5-dev \
    libbz2-dev \
    liblzma-dev \
    libglib2.0-0 \  
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your app
COPY . .

EXPOSE 5000
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "web_app:app"]

