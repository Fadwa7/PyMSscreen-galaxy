import os

# === Base working directory (from .env / docker-compose) ===
BASE_WORKING_DIR = os.getenv("WORKING_DIR", "/app/uploads")
BASE_WORKING_DIR = os.path.abspath(os.path.expanduser(BASE_WORKING_DIR))

print("BASE_WORKING_DIR =", BASE_WORKING_DIR)

PORT = int(os.getenv("PORT", "8080"))
SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkey")