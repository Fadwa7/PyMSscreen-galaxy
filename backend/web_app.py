from flask import Flask, send_file, request, jsonify
from flask_cors import CORS
import os
import json
import urllib.parse
import pandas as pd
import numpy as np
import yaml
from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors


app = Flask(__name__)
app.secret_key = 'supersecretkey'
CORS(app, supports_credentials=True, origins="*")

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

def resolve_path(p):
    return os.path.expanduser(p)

@app.route('/save_state', methods=['POST'])
def save_state():
    try:
        data = request.get_json()
        print("📥 Save request data:", data)
        working_directory = os.path.expanduser(data.get("working_directory", "."))

        if not os.path.exists(working_directory):
            return jsonify({"error": "Invalid working directory"}), 400

        state = {
            "working_directory": working_directory,
            "compound_csv": os.path.join(working_directory, data.get("compound_csv", "")),
            "mzml_files": [
                {
                    "file": os.path.join(working_directory, f.get("file")),
                    "tag": f.get("tag", ""),
                    "adduct": f.get("adduct", "")
                }
                for f in data.get("mzml_files", [])
            ]
        }

        with open(os.path.join(working_directory, "state.json"), "w") as f:
            json.dump(state, f, indent=2)

        return jsonify({"message": "State saved successfully!"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/load_state', methods=['POST'])
def load_state():
    try:
        data = request.get_json()
        working_directory = os.path.expanduser(data.get("working_directory", "."))
        state_path = os.path.join(working_directory, "state.json")

        if not os.path.exists(state_path):
            return jsonify({"error": "No saved state found."}), 404

        with open(state_path, "r") as f:
            state = json.load(f)

        return jsonify(state)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/generate_table', methods=['POST'])
def generate_table():
    try:
        body = request.get_json(force=True)
        working_directory = resolve_path(body.get("workingDirectory", ""))
        print(f"📁 Working directory: {working_directory}")

        state_path = os.path.join(working_directory, "state.json")
        print(f"📄 Looking for state at: {state_path}")
        if not os.path.exists(state_path):
            return jsonify({"error": f"State file not found at {state_path}"}), 404

        with open(state_path, "r") as f:
            state = json.load(f)

        compound_csv = state.get("compound_csv", "")
        if not compound_csv:
            return jsonify({"error": "Compound CSV path is missing from state.json"}), 400

        compound_csv_path = compound_csv if os.path.isabs(compound_csv) else os.path.join(working_directory, compound_csv)
        print(f"📄 compound_csv path: {compound_csv_path}")
        if not os.path.exists(compound_csv_path):
            return jsonify({"error": f"Compound CSV file not found: {compound_csv_path}"}), 404

        compound_df = pd.read_csv(compound_csv_path)
        output_rows = []
        compound_set = os.path.splitext(os.path.basename(compound_csv))[0]

        for compound in compound_df.itertuples():
            smiles = getattr(compound, "SMILES", "")
            try:
                mol = Chem.MolFromSmiles(smiles)
                if mol is None:
                    print(f"⚠️ Invalid SMILES for ID {compound.ID}")
                    continue
                neutral_mass = Descriptors.ExactMolWt(mol)
                formula = rdMolDescriptors.CalcMolFormula(mol)
            except Exception as e:
                print(f"⚠️ Failed to parse SMILES {smiles}: {e}")
                continue

            for entry in state.get("mzml_files", []):
                mzml_filename = os.path.basename(entry.get("file", ""))
                adduct = entry.get("adduct")
                tag = entry.get("tag")

                adduct_mass = ADDUCT_MASS.get(adduct)
                if adduct_mass is None:
                    print(f"⚠️ Unknown adduct '{adduct}' for file {mzml_filename}")
                    continue

                mz = neutral_mass + adduct_mass

                row = {
                    "ID": getattr(compound, "ID"),
                    "mz": f"{mz:.6f}",
                    "rt": "",
                    "adduct": adduct,
                    "tag": tag,
                    "set": compound_set,
                    "Name": getattr(compound, "Name", ""),
                    "known": "structure",
                    "SMILES": smiles,
                    "Formula": formula,
                    "file": mzml_filename
                }
                output_rows.append(row)

        output_path = os.path.join(working_directory, "comprehensive_table.csv")
        pd.DataFrame(output_rows).to_csv(output_path, index=False)

        print(f"✅ Table saved at: {output_path}")
        return jsonify({"message": "Table generated successfully", "path": output_path})

    except Exception as e:
        print(f"❌ Error generating table: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/save_extract_config', methods=['POST'])
def save_extract_config():
    try:
        data = request.get_json()
        working_directory = resolve_path(data.get("working_directory", "."))
        print("🛠 Saving extraction config to:", working_directory)

        if not os.path.isdir(working_directory):
            return jsonify({"error": f"Working directory not found: {working_directory}"}), 400

        # Build structured config
        config_data = {
            "tolerance": {
                "ms1 coarse": f"{data['ms1_coarse_error']} Da",
                "ms1 fine": f"{data['ms1_fine_error']} ppm",
                "eic": f"{data['ms1_eic_window']} Da",
                "rt": f"{data['retention_time_window']} min"
            },
            "prescreen": {
                "ms1_int_thresh": float(data["ms1_intensity_threshold"]),
                "ms2_int_thresh": float(data["ms2_intensity_threshold"]),
                "s2n": float(data["ms1_sn_ratio"]),
                "ret_time_shift_tol": f"{data['retention_time_delay']} min"
            }
        }

        config_path = os.path.join(working_directory, "extract_config.yaml")
        with open(config_path, "w") as f:
            yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)

        return jsonify({"message": f"Saved to {config_path}"})

    except Exception as e:
        print(f"❌ Error saving extract_config.yaml: {e}")
        return jsonify({"error": str(e)}), 500
    
@app.route('/load_extraction_config', methods=['GET'])
def load_extraction_config():
    working_dir = request.args.get('working_directory')
    config_path = os.path.join(working_dir, 'extract_config.yaml')

    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        ret_time_shift_tol = config.get('ret_time_shift_tol', 0.5)
        return jsonify({'ret_time_shift_tol': ret_time_shift_tol})
    except Exception as e:
        print(f"Error loading extract_config.yaml: {e}")
        return jsonify({'ret_time_shift_tol': 0.5})


@app.route("/extract_data", methods=["POST"])
def extract_data():
    try:
        import pandas as pd
        from pyopenms import MSExperiment, MzMLFile
        import os, json, yaml

        req = request.get_json()
        print("📥 extract_data called with:", req)
        working_dir = resolve_path(req.get("working_directory"))
        config_path = os.path.join(working_dir, "extract_config.yaml")
        state_path = os.path.join(working_dir, "state.json")
        compound_path = os.path.join(working_dir, "comprehensive_table.csv")
        print("🔍 Looking for:")
        print(" - Config:", config_path)
        print(" - State:", state_path)
        print(" - Compounds:", compound_path)

        # Print file existence
        print("📁 Config exists?", os.path.exists(config_path))
        print("📁 State exists?", os.path.exists(state_path))
        print("📁 Table exists?", os.path.exists(compound_path))

        spectra_dir = os.path.join(working_dir, "ms2_spectra")
        os.makedirs(spectra_dir, exist_ok=True)

        with open(state_path, "r") as f:
            state = json.load(f)
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        comp_df = pd.read_csv(compound_path)

        coarse_win = float(config["tolerance"]["ms1 coarse"].replace(" Da", ""))
        fine_ppm = float(config["tolerance"]["ms1 fine"].replace(" ppm", ""))
        eic_win = float(config["tolerance"]["eic"].replace(" Da", ""))
        rt_win = float(config["tolerance"]["rt"].replace(" min", ""))

        error_summary = []

        for file_obj in state["mzml_files"]:
            mzml_path = os.path.join(working_dir, file_obj["file"])
            tag = file_obj["tag"]
            adduct = file_obj["adduct"]

            print(f"\n📂 Processing file: {mzml_path} (tag={tag}, adduct={adduct})")

            exp = MSExperiment()
            MzMLFile().load(mzml_path, exp)
            spectra = exp.getSpectra()
            ms1_spectra = [s for s in spectra if s.getMSLevel() == 1]
            ms2_spectra = [s for s in spectra if s.getMSLevel() == 2]

            for row in comp_df.itertuples():
                if row.tag != tag or row.adduct != adduct:
                    continue

                mz = float(row.mz)
                fine_delta = mz * fine_ppm / 1_000_000
                fine_low, fine_high = mz - fine_delta, mz + fine_delta

                # MS1 EIC
                eic_rt, eic_int = [], []
                for sp in ms1_spectra:
                    rt = sp.getRT() / 60
                    try:
                       mzs, ints = sp.get_peaks()
                    except Exception as e:
                        msg = f"MS1 get_peaks() failed for ID={row.ID}, RT={rt:.2f} min: {e}"
                        print(f"❌ {msg}")
                        error_summary.append(msg)
                        continue

                    intensity = sum(i for m, i in zip(mzs, ints) if fine_low <= m <= fine_high)
                    eic_rt.append(rt)
                    eic_int.append(intensity)

                eic_filename = f"{row.ID}_{adduct}_{tag}_EIC.csv"
                eic_path = os.path.join(spectra_dir, eic_filename)
                eic_df = pd.DataFrame({"rt": eic_rt, "intensity": eic_int})

                try:
                  eic_df.to_csv(eic_path, index=False)
                  print(f"✅ Saved EIC: {eic_filename}")
                except Exception as e:
                  print(f"❌ Failed to save EIC for ID={row.ID}: {e}", flush=True)  
                  print(f"❌ {msg}")
                  error_summary.append(msg) 
                
                # MS2 fragment + RT
                matched_ms2 = []
                for sp in ms2_spectra:
                    precursors = sp.getPrecursors()
                    if not precursors:
                        continue
                    p_mz = precursors[0].getMZ()
                    if abs(p_mz - mz) > coarse_win:
                        continue

                    try:
                        ms2_mzs, ms2_ints = sp.get_peaks()
                    except Exception as e:
                         msg = f"MS2 get_peaks() failed for ID={row.ID}, precursor_mz={p_mz:.4f}: {e}"
                         print(f"❌ {msg}")
                         error_summary.append(msg)
                         continue
                    if len(ms2_mzs) == 0:
                        continue

                    peak_list = ";".join(
                        f"{mz_val:.4f}:{int_val:.0f}"
                        for mz_val, int_val in zip(ms2_mzs, ms2_ints)
                    )

                    scan_id = sp.getNativeID() or f"scan_{len(matched_ms2)+1}"
                    ms2_rt = sp.getRT() / 60.0
                    total_intensity = sum(ms2_ints)

                    matched_ms2.append({
                        "scan_id": scan_id,
                        "ms2_rt": ms2_rt,
                        "ms2_intensity": total_intensity, 
                        "peak_list": peak_list
                    })

                if matched_ms2:
                    ms2_df = pd.DataFrame(matched_ms2)
                    ms2_path = os.path.join(spectra_dir, f"{row.ID}_{adduct}_{tag}_MS2.csv")
                    try:
                        ms2_df.to_csv(ms2_path, index=False)
                        print(f"✅ Saved MS2: {os.path.basename(ms2_path)}")
                    except Exception as e:
                        msg = f"Failed to save MS2 for ID={row.ID}: {e}"
                        print(f"❌ {msg}")
                        error_summary.append(msg)

        return jsonify({"status": "success", "message": "Extraction complete"})

    except Exception as e:
     import traceback
     print("❌ Error in /extract_data:", e)
     traceback.print_exc()
     return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/prescreen_data", methods=["POST"])
def prescreen_data():
    try:
        import pandas as pd
        import os, json, yaml

        req = request.get_json()
        working_directory = resolve_path(req.get("working_directory"))

        config_path = os.path.join(working_directory, "extract_config.yaml")
        compound_path = os.path.join(working_directory, "comprehensive_table.csv")
        spectra_dir = os.path.join(working_directory, "ms2_spectra")

        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        ms1_thresh = config["prescreen"]["ms1_int_thresh"]
        ms2_thresh = config["prescreen"]["ms2_int_thresh"]
        s2n = config["prescreen"]["s2n"]
        rt_tol = float(str(config["prescreen"]["ret_time_shift_tol"]).replace(" min", ""))

        compound_df = pd.read_csv(compound_path)
        summary_rows = []

        for row in compound_df.itertuples():
            base_name = f"{row.ID}_{row.adduct}_{row.tag}"
            eic_path = os.path.join(spectra_dir, f"{base_name}_EIC.csv")
            ms2_path = os.path.join(spectra_dir, f"{base_name}_MS2.csv")

            summary = {
                "ID": row.ID,
                "adduct": row.adduct,
                "tag": row.tag,
                "qa_ms1_exists": False,
                "qa_ms1_good_int": False,
                "qa_ms1_above_noise": False,
                "qa_ms2_exists": False,
                "qa_ms2_good_int": False,
                "qa_ms2_near": False,
                "qa_pass": False,
                "alignment": False,
                "ms2_sel": False,
                "ms1_rt": None,
                "ms2_rt": None
            }

            rt_peak = None

            if os.path.exists(eic_path):
                eic_df = pd.read_csv(eic_path)
                if not eic_df.empty:
                    summary["qa_ms1_exists"] = True
                    max_int = eic_df["intensity"].max()
                    mean_int = eic_df["intensity"].mean()
                    rt_peak = eic_df.loc[eic_df["intensity"].idxmax(), "rt"]
                    summary["ms1_rt"] = float(rt_peak)
                    summary["alignment"] = True
                    if max_int > ms1_thresh:
                        summary["qa_ms1_good_int"] = True
                    if max_int > mean_int * s2n:
                        summary["qa_ms1_above_noise"] = True

            if os.path.exists(ms2_path):
                ms2_df = pd.read_csv(ms2_path)
                if not ms2_df.empty:
                    summary["qa_ms2_exists"] = True
                    summary["qa_ms2_good_int"] = ms2_df["peak_list"].apply(
                        lambda x: any(float(p.split(":")[1]) > ms2_thresh for p in x.split(";") if ":" in p)
                    ).any()

                    if rt_peak is not None and "ms2_rt" in ms2_df.columns:
                        rt_diffs = abs(ms2_df["ms2_rt"] - rt_peak)
                        if (rt_diffs < rt_tol).any():
                            closest_idx = rt_diffs.idxmin()
                            summary["qa_ms2_near"] = True
                            summary["ms2_sel"] = True
                            summary["ms2_rt"] = float(ms2_df.loc[closest_idx, "ms2_rt"])
                        else:
                            summary["alignment"] = False
            else:
                summary["alignment"] = False

            flags = ["qa_ms1_exists", "qa_ms1_good_int", "qa_ms1_above_noise",
                     "qa_ms2_exists", "qa_ms2_good_int", "qa_ms2_near"]
            summary["qa_pass"] = all(summary[flag] for flag in flags)

            summary_rows.append(summary)

        summary_df = pd.DataFrame(summary_rows, columns=[
            "ID", "adduct", "tag",
            "qa_ms1_exists", "qa_ms1_good_int", "qa_ms1_above_noise",
            "qa_ms2_exists", "qa_ms2_good_int", "qa_ms2_near",
            "qa_pass", "alignment", "ms2_sel",
            "ms1_rt", "ms2_rt"
        ])

        summary_path = os.path.join(working_directory, "summary_table.csv")
        summary_df.to_csv(summary_path, index=False)

        return jsonify({"status": "success", "message": "Prescreening complete."})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/get_csv")
def get_csv():
    try:
        working_dir = os.path.expanduser(request.args.get("working_directory"))
        compound_id = request.args.get("compound_id")
        file_type = request.args.get("type")  # 'EIC' or 'MS2'
        
        # Decode URL-encoded values
        tag = urllib.parse.unquote(request.args.get("tag", ""))
        adduct = urllib.parse.unquote(request.args.get("adduct", ""))

        if not all([working_dir, compound_id, tag, adduct, file_type]):
            return "Missing parameters", 400

        spectra_dir = os.path.join(working_dir, "ms2_spectra")
        prefix = f"{compound_id}_{adduct}_{tag}_{file_type}"
        
        # Debug print path
        print(f"Looking for files in: {spectra_dir}")
        print(f"Filename prefix: {prefix}")

        matches = [f for f in os.listdir(spectra_dir) if f.startswith(prefix)]
        if not matches:
            return f"No file found matching: {prefix}", 404

        return send_file(os.path.join(spectra_dir, matches[0]), mimetype="text/csv")

    except Exception as e:
        return str(e), 500

@app.route('/load_comprehensive_table', methods=['GET'])
def load_comprehensive_table():
    try:
        working_directory = os.path.expanduser(request.args.get("working_directory", "."))
        table_path = os.path.join(working_directory, "comprehensive_table.csv")
        print("📁 Requested path:", request.args.get("working_directory"))
        print("📂 Resolved path:", table_path)

        if not os.path.exists(table_path):
            print("❌ File not found at resolved path!")
            return jsonify([])  # return empty list

        df = pd.read_csv(table_path)
        df.fillna("", inplace=True)

        compounds = df.to_dict(orient="records")
        return jsonify(compounds)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/load_summary_table', methods=['GET'])
def load_summary_table():
    try:
        working_directory = os.path.expanduser(request.args.get("working_directory", "."))
        table_path = os.path.join(working_directory, "summary_table.csv")

        if not os.path.exists(table_path):
            return jsonify([])

        df = pd.read_csv(table_path)
        df.fillna("", inplace=True)
        return jsonify(df.to_dict(orient="records"))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/save_qa_flags', methods=['POST'])
def save_qa_flags():
    try:
        import pandas as pd
        data = request.get_json()
        flags = data.get("flags", {})
        working_directory = os.path.expanduser(data.get("working_directory", "."))

        table_path = os.path.join(working_directory, "summary_table.csv")
        if not os.path.exists(table_path):
            return jsonify({"error": "summary_table.csv not found"}), 404

        df = pd.read_csv(table_path)

        for compound_key, update in flags.items():
            try:
                compound_id, adduct, tag = compound_key.split("_", 2)
            except ValueError:
                return jsonify({"error": f"Invalid compound key format: {compound_key}"}), 400

            mask = (df["ID"].astype(str) == str(compound_id)) & \
                   (df["adduct"] == adduct) & (df["tag"] == tag)

            print(f"🛠 Updating row for ID={compound_id}, adduct={adduct}, tag={tag}")
            print("➡️  Incoming flags:", update)

            for display_key, summary_key in {
                "MS1_Exists": "qa_ms1_exists",
                "MS2_Exists": "qa_ms2_exists",
                "MS1_Intensity": "qa_ms1_good_int",
                "RT_Alignment": "alignment",
                "S2N_ratio": "qa_ms1_above_noise"
            }.items():
                if display_key in update:
                    value = bool(update[display_key])
                    for idx in df[mask].index:
                        df.at[idx, summary_key] = value
                        print(f"🔄 Set {summary_key} at row {idx} = {value}")

            for idx in df[mask].index:
                all_flags = [
                    df.at[idx, "qa_ms1_exists"],
                    df.at[idx, "qa_ms1_good_int"],
                    df.at[idx, "qa_ms1_above_noise"],
                    df.at[idx, "qa_ms2_exists"],
                    df.at[idx, "qa_ms2_good_int"],
                    df.at[idx, "qa_ms2_near"]
                ]
                result = all(all_flags)
                df.at[idx, "qa_pass"] = result
                print(f"✅ qa_pass for row {idx} = {result}")

        # 🔄 Ensure booleans are saved correctly
        for col in [
            "qa_ms1_exists", "qa_ms1_good_int", "qa_ms1_above_noise",
            "qa_ms2_exists", "qa_ms2_good_int", "qa_ms2_near",
            "qa_pass", "alignment", "ms2_sel"
        ]:
            if col in df.columns:
                df[col] = df[col].astype(bool)

        print(f"💾 Writing updated summary table to: {table_path}")
        df.to_csv(table_path, index=False)
        print("✅ Save completed.")

        return jsonify({"message": f"QA flags updated in {table_path}"})

    except Exception as e:
        print(f"❌ Error saving flags: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/get_compound_plots', methods=['GET'])
def get_compound_plots():
    try:
        import numpy as np
        compound_id = request.args.get("compound_id")
        working_directory = os.path.expanduser(request.args.get("working_directory", "."))

        eic_x = np.linspace(0, 10, 100)
        eic_y = np.exp(-((eic_x - 5) ** 2) / 0.8) * 1e5

        ms2_x = np.linspace(2, 8, 50)
        ms2_y = np.exp(-((ms2_x - 5) ** 2) / 1.5) * 6e4

        frag_x = [120.1, 135.2, 150.3, 165.5, 180.7]
        frag_y = [7000, 12000, 15000, 10000, 8000]

        return jsonify({
            "eic": {"x": eic_x.tolist(), "y": eic_y.tolist()},
            "ms2": {"x": ms2_x.tolist(), "y": ms2_y.tolist()},
            "fragment": {"x": frag_x, "y": frag_y}
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/export_fragments', methods=['POST'])
def export_fragments():
    try:
        data = request.get_json()
        compound_id = data["compound_id"]
        working_directory = os.path.expanduser(data["working_directory"])

        output_path = os.path.join(working_directory, "figures", f"{compound_id}_fragments.csv")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Dummy content for now
        df = pd.DataFrame({
            "mz": [100.1, 150.2, 200.3],
            "intensity": [5000, 7000, 6500]
        })
        df.to_csv(output_path, index=False)

        return jsonify({"message": f"Exported fragment peaks to {output_path}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500



@app.route('/save_plots', methods=['POST'])
def save_plots():
    try:
        data = request.get_json()
        compound_id = data["compound_id"]
        working_directory = os.path.expanduser(data["working_directory"])

        output_path = os.path.join(working_directory, "figures", f"{compound_id}_summary.pdf")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Dummy file creation
        with open(output_path, "w") as f:
            f.write("Summary plot for " + compound_id)

        return jsonify({"message": f"Saved summary plot PDF to {output_path}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5000)
