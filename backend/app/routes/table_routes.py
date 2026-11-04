from flask import Blueprint, request, jsonify

from app.preparation import ADDUCT_MASS, prepare_data
from app.utils import get_working_dir


table_bp = Blueprint("table", __name__)


@table_bp.route('/generate_table', methods=['POST'])
def generate_table():
    """Generate the compound table for a web request."""
    try:
        body = request.get_json(force=True)
        working_directory = get_working_dir(body.get("workingDirectory"))
        payload, status = prepare_data(working_directory)
        return jsonify(payload), status
    except Exception as e:
        print(f"Error generating table: {e}")
        return jsonify({"error": str(e)}), 500
