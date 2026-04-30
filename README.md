# pyMSscreen

## Overview

pyMSscreen provides a web-based interface for initial prescreening of mass spectrometry data. It combines a Flask backend with a React frontend, and is designed to run via Docker for reproducibility. The application allows users to upload compound information and mzML files, extract chromatographic and MS/MS data using pyOpenMS, and perform automated prescreening.

## Project Structure

- **Backend**: Flask + Gunicorn server with `pyOpenMS` for mzML parsing and data processing
- **Frontend**: React (Vite) served via Nginx
- **Deployment**: Docker + Docker Compose with bind-mounted working directory

## Requirements

- Docker
- Docker Compose
- Local working directory with input files:
  - `compounds.csv`
  - One or more `.mzML` files

## Setup Instructions

### 1. Clone the repository

```bash
git clone https://gitlab.com/uniluxembourg/lcsb/eci/pymsscreen.git
cd your-repo
```

### 2. Create a `.env` file

After cloning the repository, create a `.env` file in the root of the project. This file defines the path to your local data directory, which will be mounted into the backend container at `/app/uploads`.

```bash
touch .env
```

Then, open `.env` in a text editor and add the following line:

```
UPLOADS_PATH=/absolute/path/to/your/data/folder
```

On Windows with Docker Desktop + WSL2, the path should look like(important to include "\\"):

```
UPLOADS_PATH=C:\\Users\\name\\path-to-input-data
```

Ensure that this path exists and contains:

- A `compounds.csv` file
- One or more `.mzML` files. 
- Only `.mzML` files are supported. Vendor formats (e.g., Thermo `.raw`) must be converted beforehand (e.g., using MSConvert / ProteoWizard).


The `compounds.csv` file must include the following columns:

- **`ID`** (required)  
  Unique identifier for each compound.
- **`Name`** (optional)  
  Human-readable compound name.
- **`SMILES`**  
  SMILES representation of the compound structure.
- **`mz`** 
  Neutral mass of the compound.
- **`precurso_mz`**
  precursor mass where no adduct information is required. 

At least one of **`SMILES`** or **`mz`** or **`precursor_mz`** must be provided for each compound.

### Priority Rules

- If **both `SMILES` and `mz` are provided**, the application **prioritizes `SMILES`** for compound processing.
- If only one of these fields is provided, that value will be used.

### 3. Build the Docker containers

Run the following command to build the backend and frontend images, including system libraries required by `pyOpenMS`:

```bash
docker-compose build --no-cache
```

### 4. Start the application

Start both containers using:

```bash
docker-compose up
```

This will launch:

- Frontend: http://localhost:3000
- Backend: http://localhost:5000

## Example Workflow (Use Case 1 from Manuscript)

1. Navigate to `http://localhost:3000`
2. Download the [mzML files](https://zenodo.org/records/14950291) and input [compound list](https://gitlab.com/uniluxembourg/lcsb/eci/pymsscreen/-/blob/main/example_inputs/AAs.csv?ref_type=heads). Place all the input files into a local directory (e.g., /path/to/ example-data)
3. Set this directory in your .env file (as explained above).
4. In the application UI, the Working Directory: /app/uploads/ is set by default. 
5. Upload **Input Files**:
   - The compound CSV ( e.g. AA CSV)
   - One or more `.mzML` files
6. **Tags** (Manual Input): Each mzML file requires a tag to be entered manually in the interface.
   - Tags are user-defined (e.g., WT_POS, KO_NEG, STD)
   -  They are used for identifying samples, grouping and interpretation, output naming

      **Note:**
       - Tags are not automatically extracted from filenames
       - No strict validation is applied (free text input)
       - Users should use consistent and meaningful tags, especially for larger datasets.
7. **Adduct Selection:** Selected adduct(s): [e.g., [M+H]+, [M-H]- depending on your example]
  - If you are using SMILES or neutral mass (mz) as input, you must select an adduct from the dropdown menu. The selected adduct is used to calculate the expected m/z for extraction.
  - If you are screening directly using precursor mass, selecting an adduct is not required. In this case, extraction is performed around the provided precursor m/z value.
8. Click **"Save State"**
   - This generates a `state.json` file that captures the current application state, including selected inputs and settings.
9. Click **"Load State"**
   The application reads from the previously generated **`state.json`** file.
    - The user **must select the same compound CSV and `.mzML` files** that were used to create the `state.json`.
    - Once **Load State** is clicked, the application resumes from the point where it was last saved, allowing the workflow to continue without repeating previous steps.
10. Click **"Generate Table"**
11. Proceed to the **Extraction** and **Prescreening** steps as needed
12. **Extraction** Settings
    - Mass tolerance (MS1 Fine error): [e.g., 5 ppm or specify your value]
    -  Retention time window: [e.g., ±0.5 min]
13. **Prescreening / QC Criteria**
    - Signal-to-noise threshold: 3
    - MS1 intensity threshold: 100000
    - Retention time delay: 0.5 min

      **Notes**
       - These parameters correspond to the example dataset provided via Zenodo.
       - Users should adjust these values depending on instrument type, acquisition method, and data quality.
       - The parameters are set through the GUI during runtime and stored internally in `extract_config.yaml`.

     Due to environment-specific paths (e.g., Docker-mounted working directories), these configuration files are not directly portable and are therefore not included as static examples in the repository.

14. Finally the *manual QA steps and plots are visualized in the **pyMSscreen Visualization Dashboard**

All outputs (e.g., EIC/fragment CSVs, summary tables) will be saved in the same mounted working directory.

## Troubleshooting

- `FileNotFoundError`: Ensure the path in `.env` exists and contains all required files
- `500 Internal Server Error`: Check backend logs via `docker logs backend`
- `ImportError: libgthread-2.0.so.0`: Make sure your backend Dockerfile installs `libglib2.0-0`

## Platform Compatibility Notes

This application is containerized and intended to run across Linux, macOS, and Windows systems.

- **Linux (native)**: Fully supported
- **macOS**: Fully supported with Docker Desktop
- **Windows**: Requires Docker Desktop with WSL2 backend enabled. Use Linux-style paths in `.env` (e.g., `/mnt/c/Users/...`).

Ensure Docker Desktop has access to the drive via:
- Docker Desktop → Settings → Resources → File Sharing

## Notes

- This application is currently optimized for Linux environments (due to `pyOpenMS` requirements).
- Nginx is configured to support client-side routing (e.g., `/extraction`, `/plotting`).
- All data is accessed through the bind-mounted directory specified via `.env


