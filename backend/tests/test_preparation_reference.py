"""Compare CLI output with a frozen result from the original preparation."""

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


BACKEND = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "data/preparation"
HAS_DEPENDENCIES = all(
    importlib.util.find_spec(name) is not None
    for name in ("pandas", "rdkit", "pyopenms")
)


@unittest.skipUnless(HAS_DEPENDENCIES, "Scientific dependencies unavailable")
class TestOriginalPreparationReference(unittest.TestCase):
    def setUp(self):
        import pyopenms as oms

        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name)
        self.compounds = self.project / "compounds.csv"
        self.compounds.write_bytes((FIXTURES / "compounds.csv").read_bytes())
        self.paths = [self.project / "sample_pos.mzML", self.project / "sample_neg.mzML"]
        for path, polarity in zip(self.paths, (
            oms.IonSource.Polarity.POSITIVE, oms.IonSource.Polarity.NEGATIVE,
        )):
            experiment = oms.MSExperiment()
            spectrum = oms.MSSpectrum()
            spectrum.setMSLevel(1)
            spectrum.setRT(60.0)
            spectrum.set_peaks(([100.0], [1000.0]))
            settings = spectrum.getInstrumentSettings()
            settings.setPolarity(polarity)
            spectrum.setInstrumentSettings(settings)
            experiment.addSpectrum(spectrum)
            oms.MzMLFile().store(str(path), experiment)

    def run_cli(self, compounds=None, paths=None, adducts=None):
        return subprocess.run(
            [sys.executable, str(BACKEND / "prepare_data.py"),
             "--working-directory", str(self.project),
             "--compounds", str(compounds or self.compounds),
             "--mzml", *map(str, paths or self.paths),
             *(adducts if adducts is not None else [
                 "--positive-adduct", "[M+H]+", "--positive-adduct", "[M+Na]+",
                 "--negative-adduct", "[M-H]-",
             ])],
            capture_output=True, text=True,
        )

    def test_matches_original_csv(self):
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertIn("INFO    | PyMSScreen - Data Preparation", result.stderr)
        self.assertIn("Preparation complete: 8 target rows", result.stderr)
        self.assertIn("WARNING | Skipping compound 4", result.stderr)
        self.assertEqual(result.stderr.count(str(self.project / "comprehensive_table.csv")), 1)
        self.assertNotIn("Resolved files:", result.stderr)
        self.assertNotIn("Looking for state", result.stderr)
        self.assertEqual(
            (self.project / "comprehensive_table.csv").read_bytes(),
            (FIXTURES / "expected.csv").read_bytes(),
        )

    def test_galaxy_style_named_symlinks_match_original_csv(self):
        # Original display names are links to files with opaque physical names.
        staged = self.project / "inputs"
        staged.mkdir()
        compounds = staged / "compounds.csv"
        physical_csv = self.project / "dataset_100.dat"
        self.compounds.rename(physical_csv)
        compounds.symlink_to(physical_csv)
        links = []
        for i, path in enumerate(self.paths):
            physical = self.project / f"dataset_{i}.dat"
            path.rename(physical)
            link = staged / path.name
            link.symlink_to(physical)
            links.append(link)
        result = self.run_cli(compounds, links)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            (self.project / "comprehensive_table.csv").read_bytes(),
            (FIXTURES / "expected.csv").read_bytes(),
        )

    def test_invalid_smiles_does_not_fall_back_to_mass(self):
        self.compounds.write_text("ID,SMILES,mz\n1,invalid_smiles,116.0707\n")
        result = self.run_cli()
        self.assertEqual(result.returncode, 1)
        self.assertFalse((self.project / "comprehensive_table.csv").exists())

    def test_missing_adducts_still_allow_direct_precursor(self):
        self.compounds.write_text("ID,precursor_mz\n1,123.456789\n")
        result = self.run_cli(adducts=[])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_missing_adducts_for_structure_is_an_error(self):
        self.compounds.write_text("ID,SMILES\n1,NCC(O)=O\n")
        result = self.run_cli(adducts=[])
        self.assertEqual(result.returncode, 1)
        self.assertIn("No adducts selected", result.stderr)
        self.assertIn("ERROR", result.stderr)
        self.assertNotIn("Preparation complete", result.stderr)

    def test_unknown_adduct_keeps_original_empty_output_behavior(self):
        self.compounds.write_text("ID,SMILES\n1,NCC(O)=O\n")
        result = self.run_cli(adducts=["--positive-adduct", "unsupported"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.project / "comprehensive_table.csv").read_text().strip(), "")

    def test_repeated_mzml_option_keeps_all_files(self):
        result = self.run_cli(paths=[self.paths[0]], adducts=[
            "--mzml", str(self.paths[1]),
            "--positive-adduct", "[M+H]+", "--positive-adduct", "[M+Na]+",
            "--negative-adduct", "[M-H]-",
        ])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            (self.project / "comprehensive_table.csv").read_bytes(),
            (FIXTURES / "expected.csv").read_bytes(),
        )


if __name__ == "__main__":
    unittest.main()
