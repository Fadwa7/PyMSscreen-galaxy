/**
 * @typedef {Object} ExtractConfigPayload
 * @property {string} working_directory
 * @property {number} ms1_coarse_error
 * @property {number} ms1_fine_error
 * @property {number} ms1_eic_window
 * @property {number} retention_time_window
 * @property {number} ms1_intensity_threshold
 * @property {number} ms2_intensity_threshold
 * @property {number} ms1_sn_ratio
 * @property {number} retention_time_delay
 */

/**
 * @file ExtractionPage.jsx
 * @summary UI for configuring spectral extraction and pre-screening parameters.
 *
 * @description
 * This component provides controls for:
 * - Defining MS1/MS2 extraction tolerances
 * - Configuring quality control and prescreening thresholds
 * - Triggering backend spectral extraction
 * - Running automated prescreening and alignment checks
 *
 * The component communicates with the backend to:
 * - Save extraction parameters to `extract_config.yaml`
 * - Extract MS1 EICs and MS2 spectra
 * - Generate a QA summary table (`summary_table.csv`)
 *
 * Navigation
 * ----------
 * - Back to setup page (`/`)
 * - Forward to visualization page (`/plotting`)
 */

import { useState, useEffect } from 'react';
import { useAppState } from '../context/AppStateContext';
import { saveExtractConfig, extractData, prescreenData, API_BASE } from '../api/api';
import { useNavigate } from 'react-router-dom';
import RibbonHeader from "../components/RibbonHeader";


const usePrefersDark = () => {
  const [isDark, setIsDark] = useState(
    typeof window !== 'undefined' &&
      window.matchMedia &&
      window.matchMedia('(prefers-color-scheme: dark)').matches
  );
  useEffect(() => {
    if (!window.matchMedia) return;
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = (e) => setIsDark(e.matches);
    mq.addEventListener ? mq.addEventListener('change', onChange) : mq.addListener(onChange);
    return () => {
      mq.removeEventListener ? mq.removeEventListener('change', onChange) : mq.removeListener(onChange);
    };
  }, []);
  return isDark;
};

const makeTheme = (isDark) =>
  isDark
    ? {
        bg: '#0f172a',
        panel: '#0b1220',
        panelLite: '#111827',
        text: '#e5e7eb',
        muted: '#9ca3af',
        border: '#334155',
        barBg: '#1f2937',
        barTrack: '#0b1220',
        ok: '#22c55e',
        btnPrimary: '#1f2937',
        btnPrimaryText: '#e5e7eb',
        btnGo: '#166534',
        btnGoGradFrom: '#22c55e',
        btnGoGradTo: '#86efac'
      }
    : {
        bg: '#e0f4f7',
        panel: '#ffffff',
        panelLite: '#f0faff',
        text: '#111827',
        muted: '#374151',
        border: '#D1D5DB',
        barBg: '#e0e0e0',
        barTrack: '#ffffff',
        ok: '#4caf50',
        btnPrimary: '#a7cce5',
        btnPrimaryText: '#111827',
        btnGo: '#2e7d32',
        btnGoGradFrom: '#77dd77',
        btnGoGradTo: '#aaffaa'
      };


/**
 * ExtractionPage component.
 *
 * @component
 * @returns {JSX.Element} UI for spectral extraction and prescreening configuration.
 *
 * @state {number} ms1CoarseError
 * Coarse MS1 precursor m/z tolerance (Da) used for MS2 matching.
 *
 * @state {number} ms1FineError
 * Fine MS1 tolerance (ppm) used for extracted ion chromatograms (EICs).
 *
 * @state {number} ms1EicWindow
 * Absolute m/z window (Da) for EIC construction.
 *
 * @state {number} retentionTimeWindow
 * Retention time window (minutes) used for MS1 extraction.
 *
 * @state {number} ms1IntensityThreshold
 * Minimum MS1 intensity required for QA pass.
 *
 * @state {number} ms2IntensityThreshold
 * Minimum fragment ion intensity required for MS2 QA pass.
 *
 * @state {number} ms1SnRatio
 * Signal-to-noise ratio threshold for MS1 QA.
 *
 * @state {number} retentionTimeDelay
 * Allowed retention time deviation (± minutes) between MS1 and MS2.
 *
 * @state {number} progress
 * Progress percentage displayed during extraction and prescreening.
 *
 * @state {string} status
 * Human-readable status message describing current backend operation.
 *
 * @remarks
 * - All file system access is handled by the backend.
 * - The frontend only passes numeric parameters and working directory paths.
 */

export default function ExtractionPage() {
  const navigate = useNavigate();
  const { appState } = useAppState();
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState('');
  const [showProgress, setShowProgress] = useState(false);

  const [ms1CoarseError, setMs1CoarseError] = useState(0.5);
  const [ms1FineError, setMs1FineError] = useState(5);
  const [ms1EicWindow, setMs1EicWindow] = useState(0.001);
  const [retentionTimeWindow, setRetentionTimeWindow] = useState(0.5);
  const [ms1IntensityThreshold, setMs1IntensityThreshold] = useState(100000);
  const [ms2IntensityThreshold, setMs2IntensityThreshold] = useState(2500);
  const [ms1SnRatio, setMs1SnRatio] = useState(3);
  const [retentionTimeDelay, setRetentionTimeDelay] = useState(0.5);
  const isDark = usePrefersDark();
  const theme = makeTheme(isDark);


  /**
 * Save extraction and prescreening parameters to the backend.
 *
 * @async
 * @function handleSaveSettings
 * @returns {Promise<void>}
 *
 * @sideEffects
 * - Writes `extract_config.yaml` to the working directory on the backend.
 * - Displays success or failure alerts to the user.
 *
 * @remarks
 * Parameter values are explicitly cast to floating-point numbers
 * before being sent to the backend.
 */

  const handleSaveSettings = async () => {
    const config = {
      working_directory: appState.working_directory,
      ms1_coarse_error: parseFloat(ms1CoarseError),
      ms1_fine_error: parseFloat(ms1FineError),
      ms1_eic_window: parseFloat(ms1EicWindow),
      retention_time_window: parseFloat(retentionTimeWindow),
      ms1_intensity_threshold: parseFloat(ms1IntensityThreshold),
      ms2_intensity_threshold: parseFloat(ms2IntensityThreshold),
      ms1_sn_ratio: parseFloat(ms1SnRatio),
      retention_time_delay: parseFloat(retentionTimeDelay)
    };

    try {
      const res = await saveExtractConfig(config);
      alert("Settings saved to extract_config.yaml!");
    } catch (err) {
      alert("Failed to save extract_config.yaml");
    }
  };

  /**
 * Run spectral extraction followed by automated prescreening.
 *
 * @async
 * @function handleExtractAndPrescreen
 * @returns {Promise<void>}
 *
 * @workflow
 * 1) Trigger MS1/MS2 extraction (`/extract_data`)
 * 2) Monitor progress using simulated progress updates
 * 3) Trigger prescreening and QA (`/prescreen_data`)
 * 4) Display completion or error status
 *
 * @sideEffects
 * - Generates MS1 EIC and MS2 fragment CSV files
 * - Writes `summary_table.csv` to the working directory
 * - Updates progress bar and status messages in the UI
 *
 * @remarks
 * Progress updates are heuristic and do not reflect exact backend completion percentages.
 */

  const handleExtractAndPrescreen = async () => {
  setShowProgress(true);
  setProgress(5);
  setStatus('⏳ Queued job…');

  try {
    // Step 1 — Start background job
    const res = await fetch(`${API_BASE}/start_extract_prescreen`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ working_directory: appState.working_directory }),
    });
    const data = await res.json();

    if (data.error) {
      throw new Error(data.error);
    }

    const jobId = data.job_id;
    setStatus(`🧪 Job started (ID: ${jobId.slice(0, 8)})`);
    setProgress(10);

    // Step 2 — Poll every 2 seconds for updates
    const poll = setInterval(async () => {
      try {
        const r = await fetch(
          `${API_BASE}/job_status?working_directory=${encodeURIComponent(
            appState.working_directory
          )}&job_id=${jobId}`
        );
        const j = await r.json();

        if (j.error) throw new Error(j.error);

        // Update UI based on progress and state
        setProgress(j.progress || 0);
        setStatus(j.message || '');

        if (j.state === 'done') {
          clearInterval(poll);
          setProgress(100);
          setStatus('✅ Extraction & Prescreening complete & msp file generation complete!! Summary saved to summary_table.csv');
        } else if (j.state === 'error') {
          clearInterval(poll);
          setStatus(`❌ ${j.message || 'Job failed'}`);
        }
      } catch (err) {
        clearInterval(poll);
        setStatus(`❌ Failed to get status: ${err.message}`);
      }
    }, 2000);
  } catch (err) {
    setProgress(0);
    setStatus(`❌ Failed to start: ${err.message}`);
  }
};


  return (
      <div className="landing-page-wrapper" style={{ backgroundColor: theme.bg, minHeight: "100vh" }}>

   <RibbonHeader isDark={isDark} />

      <div style={{ textAlign: "center", marginTop: 35 }}>
  <h1
    style={{
      fontSize: "2.8rem",
      fontWeight: 800,
      color: theme.text,
      letterSpacing: "1px",
      textShadow: isDark
        ? "0 0 12px rgba(180,200,255,0.35)"
        : "none",
    }}
  >
    pyMSscreen
  </h1>


      {/* Subtitle */}
      <h2
        style={{
          marginTop: 12,
          fontSize: "1.6rem",
          fontWeight: 600,
          color: theme.muted,
          position: "relative",
          display: "inline-block",
          paddingBottom: 6,
        }}
      >
        Extraction & Prescreening 

        <span
          style={{
            position: "absolute",
            left: 0,
            bottom: 0,
            width: "100%",
            height: "3px",
            borderRadius: 4,
            background: isDark
              ? "linear-gradient(90deg, #5daeff, #ff4f4f)"
              : "linear-gradient(90deg, #0077ff, #ff0066)",
            backgroundSize: "200% 100%",
            animation: "header-underline 3s infinite linear",
          }}
        ></span>
      </h2>
    </div>

    {/* INTRO BLOCK */}
    <div
      className="intro"
      style={{
        padding: "20px",
        textAlign: "center",
        color: theme.muted,
      }}
    >
      <p>
        The Extraction & Prescreening module isolates the extracted ion chromatograms
        (EICs) and retrieves the corresponding MS2 spectra for each target compound
        by screening the mzML files for precursor signals within the defined mass
        tolerance. The prescreening step then applies a set of quality-control criteria to these extracted spectra, removing
        low-intensity, noisy or misaligned peaks. This ensures that only high-quality MS2 spectra advance to downstream interpretation and
        analysis.
      </p>
    </div>

      <div style={{ padding: '20px', textAlign: 'center', maxWidth: '90%', margin: 'auto' }}>
        <details style={{ background: theme.panelLite, padding: '10px', borderRadius: '8px', border: `1px solid solid ${theme.border}`, color: theme.text }}>
          <summary style={{ cursor: 'pointer', fontWeight: 'bold', color: theme.text }}>ℹ️ Extraction & Prescreening Instructions</summary>
          <ol style={{ paddingLeft: '20px', marginTop: '10px', textAlign: 'left' }}>
            <li>Default parameters for <strong>spectral extraction</strong> and <strong>prescreening</strong> are shown under their respective sections below.</li>
            <li>After saving, the configuration is written to <code>extract_config.yaml</code> in the working directory.</li>
            <li>Proceed with <strong>Extraction & Prescreening</strong> — this may take time depending on the number of compounds.</li>
            <li>Upon completion, a <code>summary_table.csv</code> file containing quality control results will be saved in the working directory.</li>
            <li>Once the summary table is available, proceed to the <strong>Visualization</strong> step to explore the spectral data.</li>
          </ol>
        </details>
      </div>

      <div style={{ display: 'flex', justifyContent: 'center', gap: '20px', maxWidth: '90%', margin: 'auto' }}>
        <div style={{ padding: '20px', backgroundColor: theme.panel, color: theme.text, borderRadius: '12px', boxShadow: '0 6px 12px rgba(0, 0, 0, 0.15)', border: `2px solid ${theme.border}`, flex: 1 }}>
          <h2>Spectral Extraction Parameters</h2>
          <label>MS1 Coarse Error (Da):</label>
          <input type="number" value={ms1CoarseError} onChange={e => setMs1CoarseError(e.target.value)} style={{ width: '100%', backgroundColor: theme.panelLite, color: theme.text, border: `1px solid ${theme.border}`, borderRadius: 6 }} />
          <label>MS1 Fine Error (ppm):</label>
          <input type="number" value={ms1FineError} onChange={e => setMs1FineError(e.target.value)} style={{ width: '100%', backgroundColor: theme.panelLite, color: theme.text, border: `1px solid ${theme.border}`, borderRadius: 6 }} />
          <label>MS1 EIC Window (Da):</label>
          <input type="number" value={ms1EicWindow} onChange={e => setMs1EicWindow(e.target.value)} style={{ width: '100%', backgroundColor: theme.panelLite, color: theme.text, border: `1px solid ${theme.border}`, borderRadius: 6 }} />
          <label>Retention Time Window (min):</label>
          <input type="number" value={retentionTimeWindow} onChange={e => setRetentionTimeWindow(e.target.value)} style={{ width: '100%', backgroundColor: theme.panelLite, color: theme.text, border: `1px solid ${theme.border}`, borderRadius: 6 }} />
        </div>

        <div style={{ padding: '20px', backgroundColor: theme.panel, color: theme.text, borderRadius: '12px', boxShadow: '0 6px 12px rgba(0, 0, 0, 0.15)', border: `2px solid ${theme.border}`, flex: 1 }}>
          <h2>Pre-screening Parameters</h2>
          <label>MS1 Intensity Threshold (MS1):</label>
          <input type="number" value={ms1IntensityThreshold} onChange={e => setMs1IntensityThreshold(e.target.value)} style={{ width: '100%', backgroundColor: theme.panelLite, color: theme.text, border: `1px solid ${theme.border}`, borderRadius: 6 }} />
          <label>MS2 Intensity Threshold (MS2):</label>
          <input type="number" value={ms2IntensityThreshold} onChange={e => setMs2IntensityThreshold(e.target.value)} style={{ width: '100%', backgroundColor: theme.panelLite, color: theme.text, border: `1px solid ${theme.border}`, borderRadius: 6 }} />
          <label>MS1 Signal-to-Noise Ratio:</label>
          <input type="number" value={ms1SnRatio} onChange={e => setMs1SnRatio(e.target.value)} style={{ width: '100%', backgroundColor: theme.panelLite, color: theme.text, border: `1px solid ${theme.border}`, borderRadius: 6 }} />
          <label>Retention Time Delay (+/- min):</label>
          <input type="number" value={retentionTimeDelay} onChange={e => setRetentionTimeDelay(e.target.value)} style={{ width: '100%', backgroundColor: theme.panelLite, color: theme.text, border: `1px solid ${theme.border}`, borderRadius: 6 }} />
        </div>
      </div>

      {showProgress && (
        <div style={{ width: '40%', margin: '20px 0 0 5%', textAlign: 'left' }}>
          <div style={{ border: `1px solid ${theme.border}`, borderRadius: '8px', padding: '10px', backgroundColor: theme.panel, color: theme.text }}>
            <div style={{ width: '100%', height: '24px', backgroundColor: theme.barBg, borderRadius: '4px', overflow: 'hidden' }}>
              <div style={{ width: `${progress}%`, height: '100%', backgroundColor: theme.ok, transition: 'width 0.3s ease-in-out' }}></div>
            </div>
            <div style={{ marginTop: '8px', fontWeight: 'bold' }}>
              Current Progress: {progress.toFixed(1)}%
            </div>
            {status && (
              <div style={{ marginTop: '4px', color: status.includes('❌') ? '#ef4444' : '#0077b6' }}>
                {status}
              </div>
            )}
          </div>
        </div>
      )}

      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', maxWidth: '90%', margin: '20px auto' }}>
        <button
          onClick={handleSaveSettings}
          style={{
            padding: '10px 15px',
            borderRadius: '5px',
            background: `linear-gradient(to bottom, ${theme.btnGoGradFrom}, ${theme.btnGoGradTo})`,
            color: theme.btnPrimaryText,
            border: `1px solid ${theme.border}`
          }}
        >
          Save Settings
        </button>

        <button
          onClick={handleExtractAndPrescreen}
          style={{
            padding: '10px 15px',
            borderRadius: '5px',
            background: `linear-gradient(to bottom, ${theme.btnGoGradFrom}, ${theme.btnGoGradTo})`,
            fontWeight: 'bold',
            color: theme.text,
            border: `1px solid ${theme.border}`       
          }}
        >
          Extract & Prescreening
        </button>
      </div>

      <div style={{ height: '100px' }}></div>

      <div style={{ width: '100%' }}>
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          width: '100%',
          padding: '0 30px',
          boxSizing: 'border-box'
        }}>
          <button
            onClick={() => navigate('/')}
            style={{
              padding: '14px 24px',
              fontSize: '16px',
              fontWeight: 'bold',
              background: `linear-gradient(to bottom, ${theme.btnPrimary}, ${theme.btnPrimary})`,
              color: theme.btnPrimaryText,
              borderRadius: '12px',
              border: `1px solid ${theme.border}`,
              cursor: 'pointer',
              transition: '0.3s'
            }}>
            ⬅ Back to Setup
          </button>
          <button
            onClick={() => navigate('/plotting')}
            style={{
              padding: '14px 24px',
              fontSize: '16px',
              fontWeight: 'bold',
              background: `linear-gradient(to bottom, ${theme.btnPrimary}, ${theme.btnPrimary})`,
              color: theme.btnPrimaryText,
              borderRadius: '12px',
              border: `1px solid ${theme.border}`,
              cursor: 'pointer',
              transition: '0.3s'
            }}>
            Visualization 📊
          </button>
        </div>
      </div>
    </div>
  );
}
