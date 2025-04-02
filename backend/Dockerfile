FROM python:3.8-slim

# Install system dependencies required for pyopenms
RUN apt-get update && apt-get install -y \
    libglib2.0-0 \
    libgomp1 \
    libxrender1 \
    libsm6 \
    libxext6 \
    && apt-get clean

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .
EXPOSE 5000

CMD ["python", "web_app.py"]
