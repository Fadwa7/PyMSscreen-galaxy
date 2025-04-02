from flask import request, send_file, jsonify
from io import BytesIO
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from fpdf import FPDF
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os

def register_pdf_export(app):

    @app.route('/export_summary_pdf', methods=['POST'])
    def export_summary_pdf():
        compound_groups = request.json.get('compound_groups', [])
        working_dir = os.path.expanduser(request.json.get('working_directory', ''))

        if not compound_groups or not working_dir:
            return jsonify({"error": "Missing required data"}), 400

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)

        for group in compound_groups:
            fig = make_subplots(
                rows=3, cols=1, vertical_spacing=0.12,
                subplot_titles=["MS1 EIC", "MS2 RT Peak", "Fragment Spectrum"]
            )

            compounds = group.get('compounds', [])
            unique_ids = [f"{c['tag']}_{c['adduct']}" for c in compounds]
            unique_identifiers = list(set(unique_ids))
            colors = plt.cm.get_cmap('tab20', len(unique_identifiers)).colors
            color_map = {uid: f'rgb({int(r*255)},{int(g*255)},{int(b*255)})' for uid, (r,g,b,_) in zip(unique_identifiers, colors)}

            for compound in compounds:
                compound_id = compound.get('ID')
                tag = compound.get('tag', '')
                adduct = compound.get('adduct', '')
                name = compound.get('Name', compound_id)
                identifier = f"{tag}_{adduct}"
                color = color_map[identifier]

                # MS1
                eic_path = os.path.join(working_dir, "ms2_spectra", f"{compound_id}_{adduct}_{tag}_EIC.csv")
                if os.path.exists(eic_path):
                    eic_df = pd.read_csv(eic_path)
                    max_rt = eic_df.loc[eic_df['intensity'].idxmax(), 'rt']
                    fig.add_trace(go.Scatter(x=eic_df["rt"], y=eic_df["intensity"],
                                             name=f"MS1 {tag} {adduct} (RT: {max_rt:.2f})",
                                             line=dict(color=color)), row=1, col=1)

                # MS2
                ms2_path = os.path.join(working_dir, "ms2_spectra", f"{compound_id}_{adduct}_{tag}_MS2.csv")
                if os.path.exists(ms2_path):
                    ms2_df = pd.read_csv(ms2_path)
                    if not ms2_df.empty:
                        closest_idx = (ms2_df['ms2_rt'] - max_rt).abs().idxmin()
                        row = ms2_df.loc[closest_idx]
                        fig.add_trace(go.Scatter(x=[row["ms2_rt"]]*2, y=[0,1],
                                                 name=f"MS2 {tag} {adduct} (RT: {row['ms2_rt']:.2f})",
                                                 line=dict(color=color, dash='dash')),
                                      row=2, col=1)

                        peaks = [tuple(map(float, p.split(':'))) for p in row.get("peak_list", "").split(';') if ':' in p]
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
            temp_img_path = f"/tmp/{group.get('group_name','group_plot')}.png"
            with open(temp_img_path, 'wb') as f:
                f.write(img_bytes)

            pdf.add_page()
            pdf.set_font("Arial", size=12)
            pdf.cell(0, 10, f"Compound Group: {group.get('group_name','Unnamed')}", ln=True)
            pdf.ln(20)
            pdf.image(temp_img_path, x=10, w=180)
            os.remove(temp_img_path)

        pdf_bytes = pdf.output(dest='S').encode('latin-1')
        output = BytesIO(pdf_bytes)
        output.seek(0)
        return send_file(output, as_attachment=True, download_name="summary_report.pdf", mimetype='application/pdf')
