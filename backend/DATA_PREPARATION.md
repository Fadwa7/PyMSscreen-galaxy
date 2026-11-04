# Data Preparation CLI

Run from the repository root, using the Python environment containing pandas,
RDKit and pyOpenMS:

```bash
python3 backend/prepare_data.py \
  --working-directory /path/to/results \
  --compounds /path/to/compounds.csv \
  --mzml /path/to/sample_pos.mzML /path/to/sample_neg.mzML \
  --positive-adduct '[M+H]+' \
  --negative-adduct '[M-H]-'
```

The output directory must exist. Supply all mzML paths after one `--mzml`.
Repeated occurrences are also combined, so earlier files are never silently
lost. Quote paths containing spaces. Relative paths are interpreted from the
shell's current directory.

No samples TSV is used. Tags are generated from the mzML filenames using the
initial selection rules in `frontend/src/utils/autoTag.js`. Common filename
parts are removed, polarity is retained, numbered runs are shortened and suffixes
make tags unique. Suggestions depend on the selected files and their order.
They do not recover tags manually edited in an earlier web session.

For `A251105_QCHLMtx02_pos_RPLCqexactive_BPI.mzML` and
`A251105_QCHLMtx01_pos_RPLCqexactive_BPI.mzML`, the tags are `QCHLMtx02_pos`
and `QCHLMtx01_pos`. File/tag assignments are printed and saved in `state.json`.

Logs go to stderr with time and level (`INFO`, `WARNING`, `ERROR`). Normal output
shows the input CSV, sample tags and polarities, generated row count and output
path. Internal state paths and dictionary dumps are hidden at the default log
level. To save the log, append `2> preparation.log` to the command. No log file is
created automatically.

Repeat an adduct option to select several. Whitespace and duplicates are removed
as in the web application's state-saving code. No adduct is selected by default.
The existing calculation determines when adduct selection is required.

## Inputs and outputs

The compound CSV keeps its existing columns and interpretation: `ID`, optional
`Name`, `SMILES`, `mz`, `precursor_mz` and `rt`. This adapter does not introduce
scientific filtering or change field precedence, masses, rounding or polarity
selection.

The command writes `state.json` and `comprehensive_table.csv` in the working
directory. Explicit inputs replace the complete state, without merging an older
configuration. Existing output files are overwritten. The CSV has the existing
columns:

```text
ID,mz,rt,adduct,tag,set,Name,known,SMILES,Formula,InChIKey,file
```

The state contains absolute paths, preserving input symlink names. It is local
to the job and is not a portable input for another Galaxy job. The table records
mzML basenames in `file` and the compound CSV stem in `set`.

To reuse an existing web state without regenerating its tags:

```bash
python3 backend/prepare_data.py --working-directory /path/to/project
```

The CLI does not start Flask, React, Docker or a web server. The web route and
CLI call the same `app.preparation.prepare_data()` function. Only Data Preparation
is run; no extraction or prescreening is started.

Exit codes are 0 for preparation success, 1 for preparation/runtime failure and
2 for invalid CLI arguments. A failed calculation may leave the generated state
and an older CSV in place. Use a fresh directory per analysis and check the exit
code; the existence of an output file alone does not establish success.

## Galaxy staging contract

The future wrapper must stage the CSV and each collection element under the
original display name, for example with named symlinks to Galaxy's physical
`dataset_*.dat` files. Both automatic tags and output names depend on this.
Symlinks are followed for reading and duplicate checks, but their names are
retained in the state and the result table. Input order must be deterministic.
Duplicate physical mzML inputs and inputs aliasing output paths are rejected.

The wrapper will pass `--working-directory .`, declare the CSV output, and check
the process exit code. It must declare the scientific dependencies. No wrapper
or Planemo configuration has been created yet.

## Scientific behavior retained

The following inherited behaviors are deliberately unchanged:

- `precursor_mz` takes priority over SMILES, then `mz`.
- Adduct mass is added for valid SMILES; `mz` alone is used directly.
- Invalid SMILES do not fall back to a supplied `mz`.
- Direct precursor targets apply to every file, regardless of polarity.
- Unsupported adducts or unknown polarities can omit targets. Zero targets can
  still return success and produce a CSV without headers.
- Missing or broken pyOpenMS can become unknown polarity in the existing helper.
- pandas infers CSV column types, including numeric identifiers.

Changing these rules, including whether empty/incomplete results should be a
fatal error, requires scientific approval. A successful CLI invocation alone
must not be described as proof that every input target was processed.

## Verification

```bash
python3 -m unittest discover -s backend/tests -p test_auto_tag.py -v
python3 -m unittest discover -s backend/tests -p test_prepare_data_cli.py -v
python3 -m unittest discover -s backend/tests -p test_preparation_reference.py -v
```

`tests/data/preparation/expected.csv` was generated from the original committed
`generate_table()` implementation. Only its HTTP envelope was replaced to run
without Flask; scientific imports and calculations were retained. The source
commit, dependency versions and generation method are in `reference.json`.
Do not regenerate this reference from the new implementation.

Tests compare CSV bytes against this independent reference, including named
symlinks over opaque Galaxy paths, both polarities, multiple adducts, mass and
precursor modes. Additional checks cover argument errors and inherited failure
behavior. Full Flask tests require Flask; direct Python/JavaScript tag comparison
requires Node.js. Missing dependencies are reported as skips.

The reference uses pandas 3.1.0, NumPy 2.5.4, RDKit 2026.9.1 and pyOpenMS 3.6.0.
These record the tested environment, not the unknown versions of a previously
deployed application. Versions for Galaxy deployment must be chosen and fixed
against the validated reference environment. The repository's general web
requirements are not changed here.

Small generated mzML files do not replace qualification on representative user
data. Flask/React integration, JavaScript tag parity and actual Galaxy execution
must be checked in their respective environments before production acceptance.

The CLI was also compared with the original committed preparation on the two
user-provided QCHLMtx mzML files and `precursor_mz.csv`. The original calculation
used the same minimal HTTP substitutes as the frozen reference generation.
The CLI used named symlinks and automatic tags. Both produced 8,152 rows with
byte-for-byte identical CSV output. All generated files were in a temporary
directory; input files and existing user results were left unchanged.

The three test suites above completed with 21 tests passing and 5 skipped:
four require Flask and one requires Node.js. No package was installed. These
results support proceeding to wrapper development, not production acceptance.
