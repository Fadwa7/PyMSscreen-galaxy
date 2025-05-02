import { useState, useEffect } from 'react';
import { saveState, loadState, generateTable } from '../api/api';
import { useAppState } from '../context/AppStateContext';
import { useNavigate } from 'react-router-dom';

const LandingPage = () => {
  const { appState, updateAppState } = useAppState();
  const [draggedRowIndex, setDraggedRowIndex] = useState(null);

  
  useEffect(() => {
  if (appState.working_directory && mzmlFiles.length === 0) {
    setWorkingDirectory(appState.working_directory || '');

    const files = appState.mzml_files.map(f => ({ name: f.file.split('/').pop() }));
    setMzmlFiles(files);

    const loadedTags = {};
    const loadedAdducts = {};
    appState.mzml_files.forEach(f => {
      const fname = f.file.split('/').pop();
      loadedTags[fname] = f.tag;
      loadedAdducts[fname] = f.adduct;
    });

    setTags(loadedTags);
    setAdductSelections(loadedAdducts);
  }
}, [appState]);


  const navigate = useNavigate();
  const [workingDirectory, setWorkingDirectory] = useState('');
  const [compoundCSV, setCompoundCSV] = useState(null);
  const [mzmlFiles, setMzmlFiles] = useState([]);
  const [tags, setTags] = useState({});
  const [adductSelections, setAdductSelections] = useState({});

  const adducts = [
    '[M+H]+', '[M+Na]+', '[M+K]+', '[M-H]-', '[M+NH4]+',
    '[M+CH3OH+H]+', '[M+ACN+H]+', '[M+ACN+Na]+', '[M+2ACN+H]+',
    '[M+Cl]-', '[M+HCOO]-', '[M+CH3COO]-'
  ];

  const handleSetWorkingDirectory = () => {
    const compoundName = compoundCSV?.name || '';
    const mzmlData = mzmlFiles.map(file => ({
      file: file.name,
      tag: tags[file.name] || '',
      adduct: adductSelections[file.name] || '[M+H]+'
    }));

    updateAppState({
      working_directory: workingDirectory,
      compound_csv: compoundName,
      mzml_files: mzmlData
    });

    alert("Working directory and files stored in context.");
  };

const handleSaveState = async () => {
  const compoundName = compoundCSV?.name || '';
  const mzmlData = mzmlFiles.map(file => ({
    file: file.name,
    tag: tags[file.name] || '',
    adduct: adductSelections[file.name] || '[M+H]+'
  }));

  const updatedState = {
    working_directory: workingDirectory,
    compound_csv: compoundName,
    mzml_files: mzmlData
  };

  // First update React context
  updateAppState(updatedState);

  // Then save to backend
  try {
    const res = await saveState({ ...appState, ...updatedState });
    alert("State updated and saved successfully!");
  } catch (err) {
    console.error("Save failed:", err);
    alert("Save failed.");
  }
};

  const handleLoadState = async () => {
    try {
      const res = await loadState({ working_directory: workingDirectory });
      const data = res.data;
      updateAppState(data);
      setWorkingDirectory(data.working_directory || '');

      const files = data.mzml_files.map(f => ({ name: f.file.split('/').pop() }));
      setMzmlFiles(files);

      const loadedTags = {};
      const loadedAdducts = {};
      data.mzml_files.forEach(f => {
        const fname = f.file.split('/').pop();
        loadedTags[fname] = f.tag;
        loadedAdducts[fname] = f.adduct;
      });

      setTags(loadedTags);
      setAdductSelections(loadedAdducts);

      alert('State loaded!');
    } catch (err) {
      console.error("Load failed:", err);
      alert('Failed to load state.');
    }
  };

  const handleGenerateTable = async () => {
    try {
      const res = await generateTable({workingDirectory});
      alert('Table generated successfully!');
    } catch (err) {
      console.error("Table generation failed:", err);
      alert("Failed to generate table.");
    }
  };
 
  const handleDeleteRow = (fileName) => {
  setMzmlFiles(prev => prev.filter(file => file.name !== fileName));
  setTags(prev => {
    const updated = { ...prev };
    delete updated[fileName];
    return updated;
  });
  setAdductSelections(prev => {
    const updated = { ...prev };
    delete updated[fileName];
    return updated;
  });
};

  return (
    <div className="min-h-screen" style={{ backgroundColor: '#e0f4f7', fontFamily: 'sans-serif' }}>
      <div className="header" style={{ textAlign: 'center', backgroundColor: '#f0f0f0', padding: '20px' }}>
        <img src="/images/Title.jpg" alt="Title Image" style={{ maxWidth: '100%', height: '350px', margin: 'auto' }} />
        <h1>Mass Spectrometry Data Pre-screening</h1>
      </div>

      <div className="intro" style={{ padding: '20px', textAlign: 'center' }}>
        <p>
          An application intended to give the user a first look into raw mass-spectrometry data. This currently means that,
          given the input of data files and a list of masses of known or unknown compounds, the application is going to
          produce MS1 and MS2 chromatograms of the substances in the list, as well as the MS2 spectra.
        </p>
      </div>

      <div className="data-config" style={{
        padding: '20px', backgroundColor: '#ffffff', margin: '20px auto', borderRadius: '12px',
        boxShadow: '0 6px 12px rgba(0, 0, 0, 0.15)', border: '2px solid #cceeff', maxWidth: '90%', width: 'fit-content'
      }}>
        <h2>Data Configuration</h2>

        <div style={{ marginBottom: '10px' }}>
          <details style={{ background: '#f0faff', padding: '10px', borderRadius: '8px', border: '1px solid #cceeff' }}>
            <summary style={{ cursor: 'pointer', fontWeight: 'bold' }}>ℹ️ Instructions</summary>
            <ol style={{ paddingLeft: '20px', marginTop: '10px' }}>
              <li>Set the <strong>Working Directory</strong> by pasting the full path containing the Compound CSV and mzML files.</li>
              <li>Upload the <strong>Compound CSV</strong> (should include <em>ID</em>, <em>Name</em>, <em>SMILES</em> — or <em>ID</em> and <em>mz</em> for suspect screening).</li>
              <li>Upload one or more <strong>mzML Files</strong>.</li>
              <li>Edit <strong>Tags</strong> (unique labels for each file) and select the appropriate <strong>Adduct</strong>.</li>
              <li>Click <strong>"Save State"</strong> to store the configuration, and <strong>"Generate Table"</strong> to proceed.</li>
              <li><em>Optional:</em> If the same working directory is specified, click <strong>"Load State"</strong> to retrieve your previously saved configuration.</li>
              <li>Once the table is successfully generated, proceed to the <strong>Extraction & Prescreening</strong> step.</li>
            </ol>
          </details>
        </div>

        <label>Working Directory:</label>
        <input type="text" value={workingDirectory} onChange={(e) => setWorkingDirectory(e.target.value)} style={{ width: '100%' }} />

        <label>Compound CSV:</label>
        <input type="file" accept=".csv" onChange={(e) => setCompoundCSV(e.target.files[0])} />

        <label>mzML Files:</label>
        <input type="file" accept=".mzML" multiple onChange={(e) => setMzmlFiles([...e.target.files])} />

      </div>

      <table style={{ width: '90%', margin: 'auto', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ backgroundColor: '#f2f2f2' }}>
            <th style={{ border: '1px solid #ddd', padding: '8px' }}>File Name</th>
            <th style={{ border: '1px solid #ddd', padding: '8px' }}>Adduct</th>
            <th style={{ border: '1px solid #ddd', padding: '8px' }}>Tag</th>
            <th style={{ border: '1px solid #ddd', padding: '8px' }}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {mzmlFiles.map((file, idx) => (
            <tr 
              key={idx}
              draggable
              onDragStart={() => setDraggedRowIndex(idx)}
              onDragOver={(e) => e.preventDefault()}
              onDrop={() => {
                const updatedFiles = [...mzmlFiles];
                const dragged = updatedFiles.splice(draggedRowIndex, 1)[0];
                updatedFiles.splice(idx, 0, dragged);
                setMzmlFiles(updatedFiles);
              }}
              style={{ border: '1px solid #ddd', padding: '8px', cursor: 'move' }}
             >
              <td style={{ border: '1px solid #ddd', padding: '8px' }}>{file.name}</td>
              <td style={{ border: '1px solid #ddd', padding: '8px' }}>
                <select
                  value={adductSelections[file.name] || ''}
                  onChange={(e) => setAdductSelections(prev => ({ ...prev, [file.name]: e.target.value }))}
                  style={{ width: '100%', padding: '5px' }}
                >
                  {adducts.map((adduct, i) => (
                    <option key={i} value={adduct}>{adduct}</option>
                  ))}
                </select>
              </td>
              <td style={{ border: '1px solid #ddd', padding: '8px' }}>
                <input
                  type="text"
                  value={tags[file.name] || ''}
                  onChange={(e) => setTags(prev => ({ ...prev, [file.name]: e.target.value }))}
                  style={{ width: '100%', padding: '5px' }}
                />
              </td>
              <td style={{ border: '1px solid #ddd', padding: '8px' }}>
		              <button onClick={() => handleDeleteRow(file.name)} style={{ color: 'red' }}>Delete</button>
	            </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div style={{ display: 'flex', justifyContent: 'flex-start', maxWidth: '90%', margin: '20px auto' }}>
        <button onClick={handleSaveState} style={{ padding: '10px 15px', marginRight: '5px', borderRadius: '5px', background: 'linear-gradient(to bottom, #a7cce5, #bfe1f2)' }}>Save State</button>
        <button onClick={handleLoadState} style={{ padding: '10px 15px', marginRight: '5px', borderRadius: '5px', background: 'linear-gradient(to bottom, #a7cce5, #bfe1f2)' }}>Load State</button>
        <button onClick={handleGenerateTable} style={{ padding: '10px 15px', borderRadius: '5px', background: 'linear-gradient(to bottom, #a7cce5, #bfe1f2)' }}>Generate Table</button>
      </div>

      <div style={{ textAlign: 'right', maxWidth: '90%', margin: 'auto', marginTop: '20px' }}>
        <button onClick={() => navigate('/extraction')} style={{ padding: '10px 15px', borderRadius: '5px', background: 'linear-gradient(to bottom, #a7cce5, #bfe1f2)' }}>
          Go to Extraction & Prescreening
        </button>
      </div>
    </div>
  );
};

export default LandingPage;
