"""CLI isolation checks and byte-for-byte comparison with the Flask adapter."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


BACKEND = Path(__file__).resolve().parents[1]
CLI = BACKEND / "prepare_data.py"
sys.path.insert(0, str(BACKEND))
HAS_PREPARATION_DEPS = all(
    importlib.util.find_spec(name) is not None
    for name in ("flask", "pandas", "rdkit")
)


def run_cli(directory):
    return subprocess.run(
        [sys.executable, str(CLI), "--working-directory", str(directory)],
        capture_output=True,
        text=True,
    )


class TestExplicitPreparationInputs(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name)
        self.compounds = self.project / "compounds.csv"
        self.compounds.write_text("ID,SMILES\n1,NCC(O)=O\n", encoding="utf-8")
        self.paths = [self.project / "sample_pos.mzML", self.project / "sample_neg.mzML"]
        for path in self.paths:
            path.touch()
        spec = importlib.util.spec_from_file_location("prepare_data_cli", CLI)
        self.cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.cli)

    def state(self):
        return self.cli.build_state(
            self.compounds, self.paths, self.project,
            ["[M+H]+", "[M+Na]+"], ["[M-H]-"],
        )

    def test_automatic_tags_and_state_format(self):
        state = self.state()
        self.assertEqual(state["mzml_files"], [
            {"file": str(self.paths[0]), "tag": "pos"},
            {"file": str(self.paths[1]), "tag": "neg"},
        ])
        self.cli.write_state(self.project, state)
        self.assertEqual(json.loads((self.project / "state.json").read_text()), state)

    def test_named_symlinks_preserve_names_and_set_source(self):
        staged = self.project / "staged"
        staged.mkdir()
        compound_link = staged / "original_compounds.csv"
        compound_link.symlink_to(self.compounds)
        links = [staged / "original_pos.mzML", staged / "original_neg.mzML"]
        for link, path in zip(links, self.paths):
            link.symlink_to(path)
        state = self.cli.build_state(compound_link, links, self.project, [], [])
        self.assertEqual(state["compound_csv"], str(compound_link))
        self.assertEqual([r["file"] for r in state["mzml_files"]], list(map(str, links)))
        self.assertEqual([r["tag"] for r in state["mzml_files"]], ["pos", "neg"])

    def test_adducts_match_web_cleanup(self):
        state = self.cli.build_state(
            self.compounds, self.paths, self.project,
            [" [M+H]+ ", "[M+H]+", "", "[M+Na]+"], [" ", "[M-H]-"],
        )
        self.assertEqual(state["adducts"], {
            "positive": ["[M+H]+", "[M+Na]+"], "negative": ["[M-H]-"],
        })

    def test_missing_and_duplicate_inputs(self):
        with self.assertRaisesRegex(ValueError, "Duplicate mzML"):
            self.cli.build_state(self.compounds, [self.paths[0]] * 2, self.project, [], [])
        alias = self.project / "alias.mzML"
        alias.symlink_to(self.paths[0])
        with self.assertRaisesRegex(ValueError, "Duplicate mzML"):
            self.cli.build_state(self.compounds, [self.paths[0], alias], self.project, [], [])
        with self.assertRaisesRegex(ValueError, "mzML file not found"):
            self.cli.build_state(self.compounds, [self.project / "missing"], self.project, [], [])
        with self.assertRaisesRegex(ValueError, "Compound CSV not found"):
            self.cli.build_state(self.project / "missing", self.paths, self.project, [], [])
        with self.assertRaisesRegex(ValueError, "At least one"):
            self.cli.build_state(self.compounds, [], self.project, [], [])

    def test_inputs_cannot_be_output_files(self):
        for name in ("state.json", "comprehensive_table.csv"):
            path = self.project / name
            path.touch()
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, "output file"):
                    self.cli.build_state(path, self.paths, self.project, [], [])
                with self.assertRaisesRegex(ValueError, "output file"):
                    self.cli.build_state(self.compounds, [path], self.project, [], [])

    def test_empty_generated_tag(self):
        path = self.project / "!.mzML"
        path.touch()
        with self.assertRaisesRegex(ValueError, "empty tag"):
            self.cli.build_state(self.compounds, [path], self.project, [], [])

    def test_partial_explicit_mode_fails_before_writing_state(self):
        result = subprocess.run(
            [sys.executable, str(CLI), "--working-directory", str(self.project),
             "--compounds", str(self.compounds)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("Explicit mode requires", result.stderr)
        self.assertFalse((self.project / "state.json").exists())

    def test_samples_option_is_removed(self):
        result = subprocess.run(
            [sys.executable, str(CLI), "--working-directory", str(self.project),
             "--samples", "samples.tsv"], capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("unrecognized arguments", result.stderr)

    @unittest.skipUnless(
        all(importlib.util.find_spec(n) is not None for n in ("pandas", "rdkit", "pyopenms")),
        "Scientific dependencies unavailable",
    )
    def test_real_mzml_matches_existing_state_with_staged_names(self):
        import pyopenms as oms

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
        reference = self.state()
        self.cli.write_state(self.project, reference)
        baseline = run_cli(self.project)
        self.assertEqual(baseline.returncode, 0, baseline.stdout + baseline.stderr)
        output = self.project / "comprehensive_table.csv"
        expected = output.read_bytes()
        output.unlink()

        staged = self.project / "staged"
        staged.mkdir()
        compound_link = staged / self.compounds.name
        compound_link.symlink_to(self.compounds)
        links = [staged / path.name for path in self.paths]
        for link, path in zip(links, self.paths):
            link.symlink_to(path)
        result = subprocess.run(
            [sys.executable, str(CLI), "--working-directory", str(self.project),
             "--compounds", str(compound_link),
             "--mzml", str(links[0]), str(links[1]),
             "--positive-adduct", " [M+H]+ ", "--positive-adduct", "[M+H]+",
             "--positive-adduct", "[M+Na]+", "--negative-adduct", "[M-H]-"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(output.read_bytes(), expected)
        state = json.loads((self.project / "state.json").read_text())
        self.assertEqual(state["compound_csv"], str(compound_link))
        self.assertEqual([r["file"] for r in state["mzml_files"]], list(map(str, links)))


class TestPreparationCLIArguments(unittest.TestCase):
    def test_help_without_scientific_dependencies(self):
        result = subprocess.run(
            [sys.executable, str(CLI), "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--working-directory", result.stdout)

    def test_missing_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = run_cli(Path(temporary) / "missing")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Working directory does not exist", result.stderr)

    def test_cli_reaches_preparation_without_web_dependencies(self):
        # Stub only scientific imports: this checks dependency isolation, not
        # scientific results, and runs even on a bare Python installation.
        source = '''
import importlib.abc
import sys
import types

class BlockWeb(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'flask', 'requests', 'gunicorn'}:
            raise AssertionError('Unexpected web dependency: ' + fullname)

sys.meta_path.insert(0, BlockWeb())
for name in ('pandas', 'rdkit', 'rdkit.Chem', 'rdkit.Chem.Descriptors',
             'rdkit.Chem.rdMolDescriptors', 'rdkit.Chem.inchi'):
    module = types.ModuleType(name)
    module.__path__ = []
    sys.modules[name] = module
sys.modules['rdkit.Chem.inchi'].MolToInchiKey = lambda mol: None
from prepare_data import main
raise SystemExit(main(['--working-directory', sys.argv[1]]))
'''
        with tempfile.TemporaryDirectory() as temporary:
            result = subprocess.run(
                [sys.executable, "-c", source, temporary],
                cwd=BACKEND,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("State file not found", result.stderr)
        self.assertNotIn("Unexpected web dependency", result.stderr)


@unittest.skipUnless(HAS_PREPARATION_DEPS, "Preparation dependencies unavailable")
class TestPreparationCLIParity(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name)
        self.state = {
            "compound_csv": "compounds.csv",
            "mzml_files": [
                {"file": "positive.mzML", "tag": "pos", "adduct": "[M+H]+"},
                {"file": "negative.mzML", "tag": "neg", "adduct": "[M-H]-"},
            ],
        }

    def write_inputs(self, csv):
        (self.project / "compounds.csv").write_text(csv, encoding="utf-8")
        (self.project / "state.json").write_text(
            json.dumps(self.state), encoding="utf-8"
        )

    def run_web_route(self):
        # Separate interpreter: each entry point reads WORKING_DIR on import.
        source = (
            "from flask import Flask\n"
            "from app.routes.table_routes import table_bp\n"
            "app = Flask(__name__)\n"
            "app.register_blueprint(table_bp)\n"
            "response = app.test_client().post('/generate_table', json={})\n"
            "print(response.get_json())\n"
            "raise SystemExit(0 if response.status_code == 200 else 1)\n"
        )
        return subprocess.run(
            [sys.executable, "-c", source],
            cwd=BACKEND,
            env={**os.environ, "WORKING_DIR": str(self.project)},
            capture_output=True,
            text=True,
        )

    def assert_output_parity(self):
        baseline = self.run_web_route()
        self.assertEqual(baseline.returncode, 0, baseline.stdout + baseline.stderr)
        output = self.project / "comprehensive_table.csv"
        expected = output.read_bytes()
        output.unlink()  # Ensure the CLI actually produces a new output.
        result = run_cli(self.project)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(output.read_bytes(), expected)

    def test_structure_mass_precursor_and_priority(self):
        self.write_inputs(
            "ID,Name,SMILES,mz,precursor_mz,RT\n"
            "1,structure,NCC(O)=O,999,,1.2\n"
            "2,mass,,116.0707,,2.3\n"
            "3,precursor,CCO,999,123.456789,3.4\n"
            "4,missing,,,,\n"
        )
        self.assert_output_parity()

    def test_current_invalid_smiles_failure_is_preserved(self):
        self.write_inputs("ID,SMILES,mz\n1,invalid_smiles,116.0707\n")
        baseline = self.run_web_route()
        result = run_cli(self.project)
        self.assertEqual(baseline.returncode, 1)
        self.assertEqual(result.returncode, 1)
        self.assertFalse((self.project / "comprehensive_table.csv").exists())

    def test_missing_state_is_an_error(self):
        result = run_cli(self.project)
        self.assertEqual(result.returncode, 1)
        self.assertIn("State file not found", result.stderr)

    @unittest.skipUnless(importlib.util.find_spec("pyopenms"), "pyOpenMS unavailable")
    def test_real_mzml_polarity_and_multiple_adducts(self):
        import pyopenms as oms

        for filename, polarity in (
            ("positive.mzML", oms.IonSource.Polarity.POSITIVE),
            ("negative.mzML", oms.IonSource.Polarity.NEGATIVE),
        ):
            experiment = oms.MSExperiment()
            spectrum = oms.MSSpectrum()
            spectrum.setMSLevel(1)
            spectrum.setRT(60.0)
            spectrum.set_peaks(([100.0], [1000.0]))
            settings = spectrum.getInstrumentSettings()
            settings.setPolarity(polarity)
            spectrum.setInstrumentSettings(settings)
            experiment.addSpectrum(spectrum)
            oms.MzMLFile().store(str(self.project / filename), experiment)
        for entry in self.state["mzml_files"]:
            entry.pop("adduct")
        self.state["adducts"] = {
            "positive": ["[M+H]+", "[M+Na]+"],
            "negative": ["[M-H]-"],
        }
        self.write_inputs("ID,Name,SMILES\n1,Glycine,NCC(O)=O\n")
        self.assert_output_parity()


if __name__ == "__main__":
    unittest.main()
