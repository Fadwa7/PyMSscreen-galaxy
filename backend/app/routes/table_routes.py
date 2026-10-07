import os
import json

import pandas as pd

from flask import Blueprint, request, jsonify

from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors
from rdkit.Chem.inchi import MolToInchiKey

from app.utils import get_working_dir, detect_polarity_mzml

table_bp = Blueprint("table", __name__)

ADDUCT_MASS = {
    "[M+H]+": 1.007276,
    "[M+Na]+": 22.989218,
    "[M+K]+": 38.963158,
    "[M-H]-": -1.007276,
    "[M+NH4]+": 18.033823,
    "[M+CH3OH+H]+": 33.033489,
    "[M+ACN+H]+": 42.033823,
    "[M+ACN+Na]+": 64.015765,
    "[M+2ACN+H]+": 83.060370,
    "[M+Cl]-": 34.969402,
    "[M+HCOO]-": 44.998201,
    "[M+CH3COO]-": 59.013851
}



@table_bp.route('/generate_table', methods=['POST'])
def generate_table():

    """
    Generate a comprehensive compound/adduct table and save it as CSV.

    This endpoint reads `state.json` from the given working directory and uses:
    - `compound_csv` (from the state) to load compounds (expects at least a
      `SMILES` column and commonly `ID`, `Name`).
    - `mzml_files` (from the state) to assign `tag` and `adduct` combinations.

    For each compound SMILES, the code computes:
    - neutral exact mass (RDKit)
    - molecular formula (RDKit)
    Then calculates m/z using a fixed adduct mass lookup (ADDUCT_MASS).

    Request JSON
    ------------
    workingDirectory : str
        Working directory containing `state.json` and the referenced `compound_csv`.

    Returns
    -------
    flask.Response
        JSON response:
        - 200: {"message": "Table generated successfully", "path": "<.../comprehensive_table.csv>"}
        - 404: if `state.json` or `compound_csv` is missing
        - 400: if `compound_csv` is missing from `state.json`
        - 500: for unexpected errors

    Side Effects
    ------------
    Writes `comprehensive_table.csv` into `workingDirectory`.

    Output Columns
    --------------
    The output CSV includes (as currently implemented):
    ID, mz, rt, adduct, tag, set, Name, known, SMILES, Formula, file

    Notes
    -----
    - Invalid SMILES are skipped.
    - Unknown adduct strings (not in ADDUCT_MASS) are skipped.
    - `rt` is left empty for downstream population.
    """

    try:
        body = request.get_json(force=True)
        working_directory = get_working_dir(body.get("workingDirectory"))
        print(f"Working directory: {working_directory}")

        state_path = os.path.join(working_directory, "state.json")
        print(f"Looking for state at: {state_path}")
        if not os.path.exists(state_path):
            return jsonify({"error": f"State file not found at {state_path}"}), 404

        with open(state_path, "r") as f:
            state = json.load(f)

        compound_csv = state.get("compound_csv", "")
        if not compound_csv:
            return jsonify({"error": "Compound CSV path is missing from state.json"}), 400

        compound_csv_path = compound_csv if os.path.isabs(compound_csv) else os.path.join(working_directory, compound_csv)
        print(f" compound_csv path: {compound_csv_path}")
        if not os.path.exists(compound_csv_path):
            return jsonify({"error": f"Compound CSV file not found: {compound_csv_path}"}), 404

        compound_df = pd.read_csv(compound_csv_path)
        # Normalize column names (case-insensitive)
        compound_df.columns = [c.strip() for c in compound_df.columns]
        compound_df.columns = [c.lower() if c.lower() in ["id", "name", "smiles", "mz", "rt", "precursor_mz"] else c for c in compound_df.columns]
        output_rows = []
        compound_set = os.path.splitext(os.path.basename(compound_csv))[0]

        # === NEW: read global adduct selections from state (can be empty lists) ===
        adducts = state.get("adducts", {}) or {}
        pos_adducts = list(adducts.get("positive") or [])
        neg_adducts = list(adducts.get("negative") or [])

        has_precursor_rows = (
            "precursor_mz" in compound_df.columns and
            compound_df["precursor_mz"].notna().any()
        )

        has_legacy = any((f.get("adduct") or "").strip() for f in state.get("mzml_files", []))
        if not has_precursor_rows and not has_legacy and not pos_adducts and not neg_adducts:
            return jsonify({"error": "No adducts selected. Choose at least one positive or negative adduct in the UI and Save State."}), 400
        
        files_resolved = []
        for entry in state.get("mzml_files", []):
            mzml_path_in_state = entry.get("file", "")
            full_mzml_path = (
                mzml_path_in_state if os.path.isabs(mzml_path_in_state)
                else os.path.join(working_directory, mzml_path_in_state)
            )
            filename = os.path.basename(full_mzml_path)
            tag = entry.get("tag")

            explicit_adduct = (entry.get("adduct") or "").strip()  # legacy support
            if explicit_adduct:
                adducts_for_file = [explicit_adduct]
                pol = "legacy"
            else:
                pol = detect_polarity_mzml(full_mzml_path)  # called ONCE per file
                if pol == "positive":
                    adducts_for_file = pos_adducts
                elif pol == "negative":
                    adducts_for_file = neg_adducts
                else:
                    adducts_for_file = []

            files_resolved.append({
                "filename": filename,
                "tag": tag,
                "adducts": adducts_for_file,
                "polarity": pol
            })

        # one concise log (instead of spamming inside the loop)
        print("Resolved files:", [
            {"file": f["filename"], "polarity": f["polarity"], "adducts": f["adducts"]}
            for f in files_resolved
        ])


        for compound in compound_df.itertuples():
            smiles = getattr(compound, "smiles", "")
            mz_from_csv = getattr(compound, "mz", None)
            rt_from_csv = getattr(compound, "rt", "")
            precursor_mz = getattr(compound, "precursor_mz", None)
            name = getattr(compound, "name", "")
            compound_id = getattr(compound, "id")

            target_mz = None
            formula = ""
            known_type = "structure"
            inchikey = ""
            is_precursor_mode = False

            # === CASE 1: direct precursor m/z provided ===
            if pd.notnull(precursor_mz):
                target_mz = float(precursor_mz)
                known_type = "feature"
                is_precursor_mode = True

            # === CASE 2: SMILES provided ===
            elif isinstance(smiles, str) and smiles.strip():
                try:
                    mol = Chem.MolFromSmiles(smiles)
                    if mol:
                        target_mz = Descriptors.ExactMolWt(mol)
                        formula = rdMolDescriptors.CalcMolFormula(mol)
                        try:
                            inchikey = MolToInchiKey(mol)
                        except Exception:
                            inchikey = ""

                    else:
                        known_type = "suspect"
                except Exception as e:
                    print(f"SMILES parse failed for ID {compound_id}: {e}")
                    known_type = "suspect"

            # === CASE 3: No SMILES, use provided m/z ===
            else:
                known_type = "suspect"
                if pd.notnull(mz_from_csv):
                    target_mz = float(mz_from_csv)
                else:
                    print(f"Missing both SMILES and m/z for ID {compound_id}")
                    continue

            for f in files_resolved:
                if is_precursor_mode:
                    row = {
                        "ID": compound_id,
                        "mz": f"{target_mz:.6f}",
                        "rt": rt_from_csv if pd.notnull(rt_from_csv) else "",
                        "adduct": "",
                        "tag": f["tag"],
                        "set": compound_set,
                        "Name": name,
                        "known": known_type,
                        "SMILES": smiles,
                        "Formula": formula,
                        "InChIKey": inchikey,
                        "file": f["filename"],
                    }
                    output_rows.append(row)
                    continue

                if not f["adducts"]:
                    continue

                for adduct in f["adducts"]:
                    adduct_mass = ADDUCT_MASS.get(adduct)
                    if adduct_mass is None:
                        print(f" Unknown adduct '{adduct}' for file {f['filename']}")
                        continue

                    mz = target_mz + adduct_mass if known_type == "structure" else target_mz

                    row = {
                        "ID": compound_id,
                        "mz": f"{mz:.6f}",
                        "rt": rt_from_csv if pd.notnull(rt_from_csv) else "",
                        "adduct": adduct,
                        "tag": f["tag"],
                        "set": compound_set,
                        "Name": name,
                        "known": known_type,
                        "SMILES": smiles,
                        "Formula": formula,
                        "InChIKey": inchikey,
                        "file": f["filename"],
                    }
                    output_rows.append(row)

        output_path = os.path.join(working_directory, "comprehensive_table.csv")
        pd.DataFrame(output_rows).to_csv(output_path, index=False)

        print(f"✅ Comprehensive table saved at: {output_path}")
        return jsonify({"message": "Table generated successfully", "path": output_path})
 
    except Exception as e:
        print(f"❌ Error generating table: {e}")
        return jsonify({"error": str(e)}), 500
