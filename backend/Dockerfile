FROM python:3.8-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .
EXPOSE 5000

CMD ["python", "web_app.py"]
