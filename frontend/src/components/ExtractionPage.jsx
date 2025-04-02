import { useState } from 'react';
import { useAppState } from '../context/AppStateContext';
import { saveExtractConfig, extractData, prescreenData } from '../api/api';
import { useNavigate } from 'react-router-dom';

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

  const handleExtractAndPrescreen = async () => {
    setShowProgress(true);
    let current = 10;
    setProgress(current);
    setStatus('⏳ Extracting data...');

    const loadingInterval = setInterval(() => {
      current += Math.random() * 5;
      if (current < 55) {
        setProgress(current);
      }
    }, 300);

    try {
      const extractRes = await extractData({ working_directory: appState.working_directory });

      if (extractRes.data.status !== 'success') {
        clearInterval(loadingInterval);
        setProgress(0);
        setStatus(`❌ Extraction failed: ${extractRes.data.message}`);
        return;
      }

      clearInterval(loadingInterval);
      setProgress(60);
      setStatus('⏳ Running prescreening...');

      let prescreenProgress = 60;
      const prescreenInterval = setInterval(() => {
        prescreenProgress += Math.random() * 5;
        if (prescreenProgress < 95) {
          setProgress(prescreenProgress);
        }
      }, 300);

      const prescreenRes = await prescreenData({ working_directory: appState.working_directory });
      clearInterval(prescreenInterval);

      if (prescreenRes.data.status === 'success') {
        setProgress(100);
        setStatus('✅ Extraction & Prescreening complete! Summary saved to summary_table.csv');
      } else {
        setProgress(60);
        setStatus(`❌ Prescreening failed: ${prescreenRes.data.message}`);
      }
    } catch (err) {
      setProgress(0);
      setStatus(`❌ Combined action failed: ${err.message}`);
    }
  };

  return (
    <div className="min-h-screen" style={{ backgroundColor: '#e0f4f7', fontFamily: 'sans-serif' }}>
      <div className="header" style={{ textAlign: 'center', backgroundColor: '#f0f0f0', padding: '20px' }}>
        <img src="/images/Title.jpg" alt="Title Image" style={{ maxWidth: '100%', height: '350px', margin: 'auto' }} />
        <h1 style={{ fontSize: '28px' }}>Extraction and Pre-screening</h1>
      </div>

      <div style={{ padding: '20px', textAlign: 'center', maxWidth: '90%', margin: 'auto' }}>
        <p>
          Spectral extraction is controlled by the parameters under the Extraction tab, while the quality check parameters are under the Prescreening tab. Configure Shinyscreen, load compound lists, and proceed to extraction and quality checks.
        </p>
      </div>

      <div style={{ display: 'flex', justifyContent: 'center', gap: '20px', maxWidth: '90%', margin: 'auto' }}>
        <div style={{ padding: '20px', backgroundColor: '#ffffff', borderRadius: '12px', boxShadow: '0 6px 12px rgba(0, 0, 0, 0.15)', border: '2px solid #cceeff', flex: 1 }}>
          <h2>Spectral Extraction Parameters</h2>
          <label>MS1 Coarse Error:</label>
          <input type="number" value={ms1CoarseError} onChange={e => setMs1CoarseError(e.target.value)} style={{ width: '100%' }} />
          <label>MS1 Fine Error:</label>
          <input type="number" value={ms1FineError} onChange={e => setMs1FineError(e.target.value)} style={{ width: '100%' }} />
          <label>MS1 EIC Window:</label>
          <input type="number" value={ms1EicWindow} onChange={e => setMs1EicWindow(e.target.value)} style={{ width: '100%' }} />
          <label>Retention Time Window (min):</label>
          <input type="number" value={retentionTimeWindow} onChange={e => setRetentionTimeWindow(e.target.value)} style={{ width: '100%' }} />
        </div>

        <div style={{ padding: '20px', backgroundColor: '#ffffff', borderRadius: '12px', boxShadow: '0 6px 12px rgba(0, 0, 0, 0.15)', border: '2px solid #cceeff', flex: 1 }}>
          <h2>Pre-screening Parameters</h2>
          <label>MS1 Intensity Threshold:</label>
          <input type="number" value={ms1IntensityThreshold} onChange={e => setMs1IntensityThreshold(e.target.value)} style={{ width: '100%' }} />
          <label>MS2 Intensity Threshold:</label>
          <input type="number" value={ms2IntensityThreshold} onChange={e => setMs2IntensityThreshold(e.target.value)} style={{ width: '100%' }} />
          <label>MS1 Signal-to-Noise Ratio:</label>
          <input type="number" value={ms1SnRatio} onChange={e => setMs1SnRatio(e.target.value)} style={{ width: '100%' }} />
          <label>Retention Time Delay (+/- min):</label>
          <input type="number" value={retentionTimeDelay} onChange={e => setRetentionTimeDelay(e.target.value)} style={{ width: '100%' }} />
        </div>
      </div>

      {showProgress && (
        <div style={{ width: '40%', margin: '20px 0 0 5%', textAlign: 'left' }}>
          <div style={{ border: '1px solid #ccc', borderRadius: '8px', padding: '10px', backgroundColor: '#fff' }}>
            <div style={{ width: '100%', height: '24px', backgroundColor: '#e0e0e0', borderRadius: '4px', overflow: 'hidden' }}>
              <div style={{ width: `${progress}%`, height: '100%', backgroundColor: '#4caf50', transition: 'width 0.3s ease-in-out' }}></div>
            </div>
            <div style={{ marginTop: '8px', fontWeight: 'bold' }}>
              Current Progress: {progress.toFixed(1)}%
            </div>
            {status && (
              <div style={{ marginTop: '4px', color: status.includes('❌') ? 'red' : '#0077b6' }}>
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
            background: 'linear-gradient(to bottom, #a7cce5, #bfe1f2)'
          }}
        >
          Save Settings
        </button>

        <button
          onClick={handleExtractAndPrescreen}
          style={{
            padding: '10px 15px',
            borderRadius: '5px',
            background: 'linear-gradient(to bottom, #77dd77, #aaffaa)',
            fontWeight: 'bold'
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
              background: 'linear-gradient(to bottom, #bde0fe, #a2d2ff)',
              borderRadius: '12px',
              border: '1px solid #90e0ef',
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
              background: 'linear-gradient(to bottom, #bde0fe, #a2d2ff)',
              borderRadius: '12px',
              border: '1px solid #90e0ef',
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
