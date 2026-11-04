"""Check CLI tags against web examples and the JavaScript implementation."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest


BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.auto_tag import compress_runs, sanitize_tag, suggest_tags


CASES = [
    (["SC07_SC08_SC09_Inlet_ACN_DCM_neg.mzML",
      "SC07_SC08_SC09_Inlet_ACN_DCM_pos.mzML",
      "SC10_SC11_SC12_Outlet_ACN_DCM_neg.mzML",
      "SC10_SC11_SC12_Outlet_ACN_DCM_pos.mzML"],
     ["SC07-09_Inlet_neg", "SC07-09_Inlet_pos",
      "SC10-12_Outlet_neg", "SC10-12_Outlet_pos"]),
    (["ISB401_AA_KO_NEG_DLD3_1.mzML", "ISB401_AA_KO_POS_DLD3_1.mzML",
      "ISB401_AA_STD_NEG_METmix_1.mzML", "ISB401_AA_STD_POS_METmix_1.mzML",
      "ISB401_AA_WT_NEG_FY4_1.mzML", "ISB401_AA_WT_POS_FY4_1.mzML"],
     ["KO_NEG_DLD3", "KO_POS_DLD3", "STD_NEG_METmix", "STD_POS_METmix",
      "WT_NEG_FY4", "WT_POS_FY4"]),
    (["A251105_QCHLMtx02_pos_RPLCqexactive_BPI.mzML",
      "A251105_QCHLMtx01_pos_RPLCqexactive_BPI.mzML"],
     ["QCHLMtx02_pos", "QCHLMtx01_pos"]),
    (["SC07_SC08_SC09_Inlet_neg.mzML"], ["SC07-09_Inlet_neg"]),
    (["same.MzML", "same.mzML"], ["same", "same_2"]),
    (["Run_é_pos.mzML", "Run_à_pos.mzML"], ["_pos", "_pos_2"]),
    ([], []),
]


class TestAutoTags(unittest.TestCase):
    def test_web_examples_and_edge_cases(self):
        for names, expected in CASES:
            with self.subTest(names=names):
                self.assertEqual(suggest_tags(names), expected)

    def test_sanitizing_and_numbered_runs(self):
        self.assertEqual(sanitize_tag(" a b/c:d*e "), "a_bcde")
        self.assertEqual(compress_runs("SC07_SC08_SC10"), "SC07-08_SC10")
        self.assertEqual(compress_runs("SC07_sc08"), "SC07_sc08")

    @unittest.skipUnless(shutil.which("node"), "Node.js unavailable for JS comparison")
    def test_matches_javascript(self):
        module = BACKEND.parent / "frontend/src/utils/autoTag.js"
        source = (
            f"import {{ suggestTags }} from {json.dumps(module.as_uri())};\n"
            f"const cases = {json.dumps([names for names, _ in CASES])};\n"
            "console.log(JSON.stringify(cases.map(names => suggestTags(names))));"
        )
        result = subprocess.run(
            [shutil.which("node"), "--input-type=module", "-e", source],
            capture_output=True, text=True, check=True,
        )
        self.assertEqual(json.loads(result.stdout), [suggest_tags(names) for names, _ in CASES])


if __name__ == "__main__":
    unittest.main()
