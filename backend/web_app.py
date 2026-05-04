import os

from flask import Flask, jsonify
from flask_cors import CORS

from app.config import BASE_WORKING_DIR, PORT, SECRET_KEY
from app.routes.state_routes import state_bp
from app.routes.table_routes import table_bp
from app.routes.extraction_routes import extraction_bp
from app.routes.data_routes import data_bp
from app.routes.pdf_export import register_pdf_export


app = Flask(__name__)
app.secret_key = SECRET_KEY

CORS(app, supports_credentials=True, origins="*")

register_pdf_export(app)

app.register_blueprint(state_bp)
app.register_blueprint(table_bp)
app.register_blueprint(extraction_bp)
app.register_blueprint(data_bp)


@app.after_request
def _no_cache(resp):
    resp.headers["Cache-Control"] = "no-store, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@app.errorhandler(500)
def handle_500(e):
    return jsonify({"status": "error", "message": "Internal Server Error"}), 500


if __name__ == "__main__":
    print("Using data directory:", BASE_WORKING_DIR)

    if not os.path.exists(BASE_WORKING_DIR):
        print("WARNING: Base directory does not exist!")

    app.run(debug=True, host="0.0.0.0", port=PORT)