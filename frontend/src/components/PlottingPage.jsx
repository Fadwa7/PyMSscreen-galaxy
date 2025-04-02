import React, { useState, useEffect, useCallback } from 'react';
import Select from 'react-select';
import axios from 'axios';
import { useAppState } from '../context/AppStateContext';
import CompoundPlot from './CompoundPlot';
import { exportCombinedPlot } from './PlotExporter';
import { exportSummaryPDF } from '../api/api';

const PlottingPage = () => {
  const { appState } = useAppState();
  const [compounds, setCompounds] = useState([]);
  const [tagOptions, setTagOptions] = useState([]);
  const [adductOptions, setAdductOptions] = useState([]);
  const [selectedTags, setSelectedTags] = useState([]);
  const [selectedAdducts, setSelectedAdducts] = useState([]);
  const [groupedByID, setGroupedByID] = useState([]);
  const [selectedGroup, setSelectedGroup] = useState(null);
  const [compoundOptions, setCompoundOptions] = useState([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [singlePlotFilename, setSinglePlotFilename] = useState('');
  const [exportPayload, setExportPayload] = useState(null);

  useEffect(() => {
    if (!appState?.working_directory) return;
    axios
      .get('http://localhost:5000/load_comprehensive_table', {
        params: { working_directory: appState.working_directory },
      })
      .then((res) => {
        const data = res.data;
        setCompounds(data);
        setTagOptions(extractUnique(data, 'tag'));
        setAdductOptions(extractUnique(data, 'adduct'));
      })
      .catch(console.error);
  }, [appState]);

  useEffect(() => {
    const tagSet = new Set(selectedTags.map(t => t.value));
    const adductSet = new Set(selectedAdducts.map(a => a.value));

    const grouped = {};
    compounds.forEach(row => {
      if (!grouped[row.ID]) grouped[row.ID] = [];
      if (
        (selectedTags.length === 0 || tagSet.has(row.tag)) &&
        (selectedAdducts.length === 0 || adductSet.has(row.adduct))
      ) {
        grouped[row.ID].push(row);
      }
    });

    const result = Object.entries(grouped).map(([id, group]) => ({ id, group }));
    setGroupedByID(result);
    setCompoundOptions(result.map(entry => ({ value: entry.id, label: `${entry.id} - ${entry.group[0]?.Name || ''}` })));
    setCurrentIndex(0);
  }, [compounds, selectedTags, selectedAdducts]);

  const extractUnique = (data, field) => {
    const set = new Set();
    data.forEach((row) => {
      (row[field]?.split(',') || []).forEach((val) => set.add(val.trim()));
    });
    return Array.from(set).map((v) => ({ value: v, label: v }));
  };

  const handlePrev = () => {
    setCurrentIndex((prev) => (prev > 0 ? prev - 1 : prev));
  };

  const handleNext = () => {
    setCurrentIndex((prev) => (prev < compoundOptions.length - 1 ? prev + 1 : prev));
  };

  const handleKeyDown = useCallback((e) => {
    if (e.key === 'ArrowLeft') handlePrev();
    else if (e.key === 'ArrowRight') handleNext();
  }, [compoundOptions]);

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  useEffect(() => {
    const selected = groupedByID.find(entry => entry.id === compoundOptions[currentIndex]?.value);
    if (selected) setSelectedGroup(selected.group);
  }, [currentIndex, compoundOptions, groupedByID]);

  const handleSaveSinglePlot = () => {
    const entry = groupedByID[currentIndex];
    const groupToUse = selectedGroup || entry?.group || [];
    if (!groupToUse.length || !appState?.working_directory) return;

    const compoundId = groupToUse[0].ID;
    const tags = [...new Set(groupToUse.map(row => row.tag))].join('_');
    const adducts = [...new Set(groupToUse.map(row => row.adduct))];
    const adductPart = adducts.length === 1 ? adducts[0] : 'multiadducts';

    const defaultName = `${compoundId}_${tags}_${adductPart}`.replace(/\s+/g, '');
    const filename = (singlePlotFilename || defaultName).trim();

    if (exportPayload) {
      exportCombinedPlot({ ...exportPayload, filename });
    } else {
      alert('Plots are not yet ready for export.');
    }
  };

  const handleExportSummaryPDF = async () => {
  if (!appState?.working_directory || groupedByID.length === 0) return;

  const compoundsToSend = groupedByID.flatMap(entry => entry.group);
  console.log("🚀 Exporting summary for:", compoundsToSend);

  try {
    const blob = await exportSummaryPDF(compoundsToSend, appState.working_directory);

    const tagStr = selectedTags.map(t => t.value).join('-') || 'alltags';
    const adductStr = selectedAdducts.map(a => a.value).join('-') || 'alladducts';
    const defaultName = `summary_${tagStr}_${adductStr}`.replace(/\s+/g, '');

    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", `${defaultName}.pdf`);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  } catch (err) {
    console.error("❌ PDF export failed:", err);
    alert("Something went wrong while exporting the summary PDF.");
  }
};

  return (
    <div style={{ minHeight: '100vh', backgroundColor: '#e0f4f7', fontFamily: 'sans-serif', display: 'flex', flexDirection: 'column' }}>
      <div style={{ textAlign: 'center', backgroundColor: '#f0f0f0', padding: '20px', borderBottom: '2px solid #ccc' }}>
        <h1 style={{ fontSize: '28px', fontWeight: 'bold', margin: 0 }}>pyMSscreen Visualization Dashboard</h1>
      </div>
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        <div style={{ width: '340px', padding: '20px', backgroundColor: '#f4f6f9', borderRight: '2px solid #ccc', display: 'flex', flexDirection: 'column' }}>
          <h2 style={{ fontSize: '18px', fontWeight: 'bold', textAlign: 'center', marginBottom: '20px' }}>Settings Pane</h2>

          <div style={{ marginBottom: '15px', zIndex: 20, position: 'relative' }}>
            <label style={{ fontSize: '14px', marginBottom: '5px', display: 'block' }}>Filter by Tag:</label>
            <Select
              isMulti
              closeMenuOnSelect={false}
              options={tagOptions}
              onChange={setSelectedTags}
              styles={{ container: base => ({ ...base, fontSize: '14px', zIndex: 20 }) }}
            />
          </div>

          <div style={{ marginBottom: '15px', zIndex: 10, position: 'relative' }}>
            <label style={{ fontSize: '14px', marginBottom: '5px', display: 'block' }}>Filter by Adduct:</label>
            <Select
              isMulti
              closeMenuOnSelect={false}
              options={adductOptions}
              onChange={setSelectedAdducts}
              styles={{ container: base => ({ ...base, fontSize: '14px', zIndex: 10 }) }}
            />
          </div>

          <div style={{ marginTop: '10px', marginBottom: '10px' }}>
            <label style={{ fontSize: '14px', marginBottom: '5px', display: 'block' }}>Select Compound:</label>
            <Select
              options={compoundOptions}
              value={compoundOptions[currentIndex] || null}
              onChange={(selected) => {
                const index = compoundOptions.findIndex(opt => opt.value === selected.value);
                if (index !== -1) setCurrentIndex(index);
              }}
              styles={{ container: base => ({ ...base, fontSize: '14px', zIndex: 5 }) }}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '8px' }}>
              <button onClick={handlePrev} style={plotButtonStyle}>Previous</button>
              <button onClick={handleNext} style={plotButtonStyle}>Next</button>
            </div>
          </div>

          {selectedGroup && (
            <div style={{ backgroundColor: '#ffffff', border: '2px solid #cceeff', borderRadius: '10px', boxShadow: '0 6px 12px rgba(0, 0, 0, 0.1)', padding: '10px' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                <thead>
                  <tr>
                    <th style={thStyle}>Tag</th>
                    <th style={thStyle}>Adduct</th>
                    <th style={thStyle}>Name</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedGroup.map((row, i) => (
                    <tr key={i} style={{ backgroundColor: i % 2 === 0 ? '#f9fcff' : '#ffffff' }}>
                      <td style={tdStyle}>{row.tag}</td>
                      <td style={tdStyle}>{row.adduct}</td>
                      <td style={tdStyle}>{row.Name}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <button onClick={() => setSelectedGroup(groupedByID[currentIndex]?.group)} style={{ ...plotButtonStyle, marginTop: '10px' }}>Plot Selected</button>
            </div>
          )}

          <div style={{ marginTop: '16px' }}>
            <label style={{ fontSize: '13px', marginBottom: '4px', display: 'block' }}>Save Plot As:</label>
            <input type="text" value={singlePlotFilename} onChange={(e) => setSinglePlotFilename(e.target.value)} placeholder="Custom filename (optional)" style={{ fontSize: '12px', padding: '6px', width: '100%', marginBottom: '8px' }} />
            <button onClick={handleSaveSinglePlot} style={{ ...plotButtonStyle, width: '100%', marginBottom: '10px' }}>💾 Save Plot</button>
            <button onClick={handleExportSummaryPDF} style={{ ...plotButtonStyle, width: '100%' }}>📄 Export Summary PDF</button>
          </div>
        </div>

        <div style={{ flex: 1, padding: '30px', backgroundColor: '#ffffff', display: 'flex', alignItems: 'center', justifyContent: 'center', borderLeft: '2px solid #ccc' }}>
          {selectedGroup ? (
            <CompoundPlot compoundGroup={selectedGroup} onExportReady={setExportPayload} />
          ) : (
            <div style={{ width: '100%', height: '100%', borderRadius: '16px', border: '2px solid #cceeff', backgroundColor: '#f9fbfc', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: 'inset 0 4px 8px rgba(0, 0, 0, 0.05)' }}>
              <p style={{ fontSize: '14px', color: '#666', fontStyle: 'italic' }}>Plots will appear here after selection</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

const thStyle = {
  padding: '6px',
  border: '1px solid #ddd',
  textAlign: 'left',
  fontWeight: '600',
  color: '#333'
};

const tdStyle = {
  padding: '6px',
  border: '1px solid #ddd'
};

const plotButtonStyle = {
  padding: '6px 12px',
  fontSize: '12px',
  fontWeight: '600',
  borderRadius: '5px',
  background: 'linear-gradient(to bottom, #a7cce5, #bfe1f2)',
  color: '#1a1a1a',
  boxShadow: '0 2px 5px rgba(0,0,0,0.1)',
  cursor: 'pointer'
};

export default PlottingPage;
