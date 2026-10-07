"""Step 2: library_all.msp with several adducts per tag, and no 'nan' text."""
import pandas as pd

from app.routes.extract_prescreen_mspgen import generate_msp_library


def _write_inputs(wd, adducts):
    summary, comp = [], []
    for adduct, mz in adducts:
        summary.append(dict(ID=101, Name="Example", adduct=adduct, tag="WT+", qa_pass=True,
                            ms2_sel=True, ms1_rt=6.28, ms2_rt=6.30, peak_list="70.0652:30592946;116.0706:9496492"))
        comp.append(dict(ID=101, mz=mz, rt=None, adduct=adduct, tag="WT+", Name="Example",
                         SMILES=None, Formula=None, InChIKey=None, file="sample.mzML"))
    pd.DataFrame(summary).to_csv(wd / "summary_table.csv", index=False)
    pd.DataFrame(comp).to_csv(wd / "comprehensive_table.csv", index=False)


def test_one_adduct_per_tag(tmp_path):
    _write_inputs(tmp_path, [("[M+H]+", 116.0707)])
    result = generate_msp_library(str(tmp_path))
    text = open(result["library_path"]).read()
    assert result["entries"] == 1
    assert "PRECURSORMZ: 116.0707" in text
    assert "RT: 6.28" in text
    assert "nan" not in text.lower()


def test_two_adducts_in_same_tag(tmp_path):
    _write_inputs(tmp_path, [("[M+H]+", 116.0707), ("[M+Na]+", 138.0526)])
    result = generate_msp_library(str(tmp_path))
    text = open(result["library_path"]).read()
    assert result["entries"] == 2
    entries = text.strip().split("\n\n")
    assert "PRECURSORTYPE: [M+H]+" in entries[0] and "PRECURSORMZ: 116.0707" in entries[0]
    assert "PRECURSORTYPE: [M+Na]+" in entries[1] and "PRECURSORMZ: 138.0526" in entries[1]
