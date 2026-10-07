from flask import request, send_file, jsonify
from io import BytesIO
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from fpdf import FPDF
import pandas as pd
import numpy as np
import matplotlib
import os
import tempfile

from app.routes.extract_prescreen_mspgen import build_feature_base
from app.utils import get_working_dir


def _clean(value):
    """Missing values (None, NaN, 'nan', 'null') -> ''."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "null"} else text


def _load_summary(working_dir):
    """
    Summary rows keyed by (ID, adduct, tag). The PDF shows the peak and MS2
    spectrum chosen in the summary table (automatic or manually reviewed),
    the same ones used for library_all.msp.
    """
    path = os.path.join(working_dir, "summary_table.csv")
    if not os.path.exists(path):
        return {}
    df = pd.read_csv(path)
    return {(_clean(r["ID"]), _clean(r.get("adduct")), _clean(r["tag"])): r
            for r in df.to_dict("records")}


def register_pdf_export(app):

    @app.route('/export_summary_pdf', methods=['POST'])
    def export_summary_pdf():
        compound_groups = request.json.get('compound_groups', [])
        working_dir = get_working_dir(request.json.get('working_directory'))

        if not compound_groups or not working_dir:
            return jsonify({"error": "Missing required data"}), 400

        summary = _load_summary(working_dir)

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)

        for group in compound_groups:
            fig = make_subplots(
                rows=3, cols=1, vertical_spacing=0.12,
                subplot_titles=["MS1 EIC", "MS2 RT Peak", "Fragment Spectrum"]
            )

            compounds = group.get('compounds', [])
            unique_ids = [f"{c.get('tag', '')}_{_clean(c.get('adduct'))}" for c in compounds]
            unique_identifiers = list(dict.fromkeys(unique_ids))  # stable order
            # plt.cm.get_cmap was removed in Matplotlib 3.9; use the colormap registry
            cmap = matplotlib.colormaps["tab20"].resampled(max(1, len(unique_identifiers)))
            color_map = {}
            for i, uid in enumerate(unique_identifiers):
                r, g, b, _ = cmap(i)
                color_map[uid] = f'rgb({int(r*255)},{int(g*255)},{int(b*255)})'

            for compound in compounds:
                compound_id = compound.get('ID')
                tag = compound.get('tag', '')
                adduct = _clean(compound.get('adduct'))
                identifier = f"{tag}_{adduct}"
                color = color_map[identifier]
                # same file naming as the extraction (rows without adduct: ID_tag)
                base = build_feature_base(compound_id, adduct, tag)
                row = summary.get((_clean(compound_id), adduct, _clean(tag)), {})
                ms1_rt = pd.to_numeric(row.get("ms1_rt"), errors="coerce")
                ms2_rt = pd.to_numeric(row.get("ms2_rt"), errors="coerce")

                # MS1
                eic_path = os.path.join(working_dir, "ms2_spectra", f"{base}_EIC.csv")
                if os.path.exists(eic_path):
                    eic_df = pd.read_csv(eic_path)
                    if not eic_df.empty:
                        rt_label = f"RT: {ms1_rt:.2f}" if pd.notna(ms1_rt) else "no peak"
                        fig.add_trace(go.Scatter(x=eic_df["rt"], y=eic_df["intensity"],
                                                 name=f"MS1 {tag} {adduct} ({rt_label})",
                                                 line=dict(color=color)), row=1, col=1)

                # MS2: the spectrum selected in the summary table
                peak_list = _clean(row.get("peak_list"))
                if pd.notna(ms2_rt) and peak_list:
                    fig.add_trace(go.Scatter(x=[ms2_rt]*2, y=[0, 1],
                                             name=f"MS2 {tag} {adduct} (RT: {ms2_rt:.2f})",
                                             line=dict(color=color, dash='dash')),
                                  row=2, col=1)

                    peaks = [tuple(map(float, p.split(':'))) for p in peak_list.split(';') if ':' in p]
                    if peaks:
                        max_int = max(y for _, y in peaks)
                        for mz, intensity in peaks:
                            fig.add_trace(go.Scatter(x=[mz, mz], y=[0, intensity/max_int],
                                                     mode='lines', line=dict(width=2, color=color),
                                                     showlegend=False), row=3, col=1)

            fig.update_layout(height=900, width=800, showlegend=True)
            fig.update_xaxes(range=[0, 30], title_text='RT (min)', row=1, col=1)
            fig.update_xaxes(range=[0, 30], title_text='RT (min)', row=2, col=1)
            fig.update_xaxes(title_text='m/z', row=3, col=1)

            fig.update_yaxes(title_text='Intensity (MS1)', tickformat='.2e', row=1, col=1)
            fig.update_yaxes(title_text='Intensity (MS2)', range=[0, 1.05], row=2, col=1)
            fig.update_yaxes(title_text='', range=[0, 1.05], showticklabels=False, row=3, col=1)

            img_bytes = fig.to_image(format="png", width=800, height=900, scale=2)
            # temporary file with a safe, unique name (group names may contain '/' etc.)
            fd, temp_img_path = tempfile.mkstemp(suffix=".png")
            try:
                with os.fdopen(fd, 'wb') as f:
                    f.write(img_bytes)

                pdf.add_page()
                pdf.set_font("Arial", size=12)
                pdf.cell(0, 10, f"Compound Group: {group.get('group_name','Unnamed')}", ln=True)
                pdf.ln(20)
                pdf.image(temp_img_path, x=10, w=180)
            finally:
                os.remove(temp_img_path)

        pdf_bytes = pdf.output(dest='S').encode('latin-1')
        output = BytesIO(pdf_bytes)
        output.seek(0)
        return send_file(output, as_attachment=True, download_name="summary_report.pdf", mimetype='application/pdf')
