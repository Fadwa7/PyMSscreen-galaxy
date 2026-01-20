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
- One or more `.mzML` files


The `compounds.csv` file must include the following columns:

- **`ID`** (required)  
  Unique identifier for each compound.
- **`Name`** (optional)  
  Human-readable compound name.
- **`SMILES`**  
  SMILES representation of the compound structure.
- **`mz`** 
  Neutral mass of the compound.

At least one of **`SMILES`** or **`mz`** must be provided for each compound.

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

## Usage Instructions

1. Navigate to `http://localhost:3000`
2. Working Directory: /app/uploads/ (this is set by default in the UI)
3. Upload **Input Files**:
   - The compound CSV
   - One or more `.mzML` files
4. Click **"Save State"**
   - This generates a `state.json` file that captures the current application state, including selected inputs and settings.
5. Click **"Load State"**
   The application reads from the previously generated **`state.json`** file.
    - The user **must select the same compound CSV and `.mzML` files** that were used to create the `state.json`.
    - Once **Load State** is clicked, the application resumes from the point where it was last saved, allowing the workflow to continue without repeating previous steps.
5. Click **"Generate Table"**
6. Proceed to the **Extraction** and **Prescreening** steps as needed
7. Finally the *manual QA steps and plots are visualized in the **pyMSscreen Visualization Dashboard**

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


