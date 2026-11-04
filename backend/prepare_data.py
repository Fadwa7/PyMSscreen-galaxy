"""Run the shared data preparation calculation without Flask or Docker."""

import argparse
import json
import logging
import os
from pathlib import Path
import sys
import tempfile


def build_state(compounds, mzml_files, working_directory,
                positive_adducts, negative_adducts):
    """Build state.json from compound and mzML inputs with automatic tags."""
    compounds = compounds.expanduser().absolute()
    if not compounds.is_file():
        raise ValueError(f"Compound CSV not found: {compounds}")
    if compounds.resolve() in {
        (working_directory / "comprehensive_table.csv").resolve(),
        (working_directory / "state.json").resolve(),
    }:
        raise ValueError("The compound CSV cannot also be an output file")

    files = []
    seen_paths = set()
    for filename in mzml_files:
        path = Path(filename).expanduser().absolute()
        if not path.is_file():
            raise ValueError(f"mzML file not found: {path}")
        resolved = path.resolve()
        if resolved in seen_paths:
            raise ValueError(f"Duplicate mzML path: {path}")
        if resolved in {
            (working_directory / "state.json").resolve(),
            (working_directory / "comprehensive_table.csv").resolve(),
        }:
            raise ValueError(f"An mzML input cannot also be an output file: {path}")
        seen_paths.add(resolved)
        files.append(path)

    from app.auto_tag import suggest_tags

    if not files:
        raise ValueError("At least one mzML file is required")
    tags = suggest_tags([path.name for path in files])
    if any(not tag for tag in tags):
        raise ValueError("A filename produces an empty tag; use a meaningful mzML filename")
    entries = [{"file": str(path), "tag": tag} for path, tag in zip(files, tags)]

    return {
        "working_directory": str(working_directory),
        "compound_csv": str(compounds),
        "mzml_files": entries,
        "adducts": {
            "positive": list(dict.fromkeys(a.strip() for a in positive_adducts if a.strip())),
            "negative": list(dict.fromkeys(a.strip() for a in negative_adducts if a.strip())),
        },
    }


def write_state(directory, state):
    """Replace state.json only after its complete contents have been written."""
    fd, name = tempfile.mkstemp(dir=directory, prefix=".state_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2)
            handle.write("\n")
        os.replace(name, directory / "state.json")
    finally:
        if os.path.exists(name):
            os.unlink(name)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Generate comprehensive_table.csv using the existing PyMSScreen "
            "preparation code. Supply explicit inputs to generate state.json, "
            "or use an existing state.json. No web server is started."
        )
    )
    parser.add_argument(
        "--working-directory",
        required=True,
        type=Path,
        help="Existing output directory (or project containing an existing state.json).",
    )
    parser.add_argument("--compounds", type=Path, help="Input compound CSV.")
    parser.add_argument(
        "--mzml", nargs="+", action="extend", metavar="PATH",
        help="mzML paths. Tags are generated from these filenames, in the given order.",
    )
    parser.add_argument(
        "--positive-adduct", action="append", default=[],
        help="Positive adduct, quoted; repeat to select several. No default adduct.",
    )
    parser.add_argument(
        "--negative-adduct", action="append", default=[],
        help="Negative adduct, quoted; repeat to select several. No default adduct.",
    )
    args = parser.parse_args(argv)
    working_directory = args.working_directory.expanduser().resolve()
    if not working_directory.is_dir():
        parser.error(f"Working directory does not exist: {working_directory}")

    explicit_inputs = any((
        args.compounds is not None,
        args.mzml is not None,
        args.positive_adduct,
        args.negative_adduct,
    ))
    state = None
    if explicit_inputs:
        if args.compounds is None or not args.mzml:
            parser.error("Explicit mode requires --compounds and --mzml")
        try:
            state = build_state(
                args.compounds, args.mzml, working_directory,
                args.positive_adduct, args.negative_adduct,
            )
        except (ValueError, OSError) as exc:
            parser.error(str(exc))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
    )
    logger = logging.getLogger("pymsscreen")
    logger.info("PyMSScreen - Data Preparation")

    try:
        from app.preparation import prepare_data

        if state is not None:
            write_state(working_directory, state)
        result, status = prepare_data(str(working_directory))
        if status != 200:
            logger.error("%s", result.get("error", str(result)))
            return 1
    except Exception as exc:
        logger.error("Data preparation failed: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
