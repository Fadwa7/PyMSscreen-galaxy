import React, { useState, useEffect, useCallback, useRef } from 'react';
import Select from 'react-select';
import axios from 'axios';
import { useAppState } from '../context/AppStateContext';
import CompoundPlot from './CompoundPlot';
import { exportCombinedPlot } from './PlotExporter';
import { exportSummaryPDF } from '../api/api';
import { saveQAFlags } from '../api/api';
import { useNavigate } from 'react-router-dom';

// --- dark mode support (inline, no CSS files) ---
const usePrefersDark = () => {
  const [isDark, setIsDark] = React.useState(
    typeof window !== 'undefined' &&
      window.matchMedia &&
      window.matchMedia('(prefers-color-scheme: dark)').matches
  );
  React.useEffect(() => {
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
        leftPane: '#0b1220',
        leftPaneBorder: '#334155',
        tableHeader: '#111827',
        tableRowA: '#0e182b',
        tableRowB: '#0b1220',
        helpBg: '#0b1220',
        helpBorder: '#334155',
        toastBg: '#1f2937',
        toastText: '#e5e7eb',
        btnGradFrom: '#2b8dd8',
        btnGradTo: '#9bd0ef',
        accentText: '#e5e7eb'
      }
    : {
        bg: '#ffffff',
        panel: '#ffffff',
        panelLite: '#f9f9f9',
        text: '#1f2937',
        muted: '#374151',
        border: '#e5e7eb',
        leftPane: '#f9f9f9',
        leftPaneBorder: '#cccccc',
        tableHeader: '#ececec',
        tableRowA: '#fafafa',
        tableRowB: '#f0f0f0',
        helpBg: '#f0faff',
        helpBorder: '#cceeff',
        toastBg: '#333333',
        toastText: '#ffffff',
        btnGradFrom: '#a7cce5',
        btnGradTo: '#bfe1f2',
        accentText: '#1a1a1a'
      };

const buttonStyle = (theme, opts = {}) => {
  const {
    variant = 'primary',     // 'primary' | 'warning' | 'neutral'
    disabled = false,
    full = false,            // full width
    size = 'md',             // 'sm' | 'md' | 'lg'
  } = opts;

  const sizes = {
    sm: { padding: '6px 10px', fontSize: 12, borderRadius: 6 },
    md: { padding: '8px 12px', fontSize: 13, borderRadius: 8 },
    lg: { padding: '12px 16px', fontSize: 16, borderRadius: 10 },
  };

  let bg;
  if (variant === 'warning') {
    bg = 'linear-gradient(to right, #f6d365, #fda085)';
  } else if (variant === 'neutral') {
    bg = `linear-gradient(to bottom, ${theme.panelLite}, ${theme.panel})`;
  } else {
    // primary
    bg = `linear-gradient(to bottom, ${theme.btnGradFrom}, ${theme.btnGradTo})`;
  }

  return {
    ...sizes[size],
    width: full ? '100%' : undefined,
    fontWeight: 700,
    background: bg,
    color: theme.accentText,
    border: `1px solid ${theme.border}`,
    boxShadow: '0 2px 5px rgba(0,0,0,0.1)',
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.5 : 1,
    transition: 'filter .15s ease',
  };
};

// Clear checkbox appearance: bigger + theme color
const checkboxStyle = {
  width: 18,
  height: 18,
  accentColor: '#60a5fa',            // blue in dark mode is very visible
  // if you prefer to follow theme strictly, use theme.ok or a brand color
  // accentColor: theme.ok,
};

const PlottingPage = () => {
  const { appState } = useAppState();
  const isDark = usePrefersDark();
  const theme = React.useMemo(() => makeTheme(isDark), [isDark]);
  const selectedIdRef = useRef(null);
  const [compounds, setCompounds] = useState([]);
  const navigate = useNavigate();
  const [summaryData, setSummaryData] = useState([]);
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
  const [qaFlags, setQaFlags] = useState({});
  const [toastMessage, setToastMessage] = useState('');
  const qaFlagsCache = useRef({});
  const isTrue = (val) => val === true || val === 'true' || val === 'True' || val === 1 || val === '1';
  const isSingleTagSelected = () => selectedTags.length === 1;

  const selectStyles = React.useMemo(() => ({
  control: (base, state) => ({
    ...base,
    backgroundColor: theme.panelLite,
    color: theme.text,
    borderColor: theme.border,
    boxShadow: state.isFocused ? `0 0 0 1px ${theme.border}` : base.boxShadow,
    '&:hover': { borderColor: theme.muted }
  }),
  menu: (base) => ({
    ...base,
    backgroundColor: theme.panel,
    color: theme.text,
    border: `1px solid ${theme.border}`,
    zIndex: 5
  }),
  option: (base, state) => ({
    ...base,
    backgroundColor: state.isSelected
      ? theme.tableRowB
      : state.isFocused
      ? theme.tableRowA
      : theme.panel,
    color: theme.text
  }),
  input: (base) => ({ ...base, color: theme.text }),
  singleValue: (base) => ({ ...base, color: theme.text }),
  placeholder: (base) => ({ ...base, color: theme.muted }),
  multiValue: (base) => ({ ...base, backgroundColor: theme.tableRowB }),
  multiValueLabel: (base) => ({ ...base, color: theme.text }),
  multiValueRemove: (base) => ({
    ...base,
    color: theme.text,
    ':hover': { backgroundColor: theme.border, color: theme.text }
  }),
  dropdownIndicator: (base) => ({ ...base, color: theme.muted }),
  clearIndicator: (base) => ({ ...base, color: theme.muted })
}), [theme]);

   
  const handleUpdateQA = () => {
    console.log("📤 Submitting QA flags:", qaFlags);  // still useful here
    saveQAFlags(appState.working_directory, qaFlags)
      .then(() => alert('✅ QA flags updated'))
      .catch(() => alert('❌ Failed to update QA flags'));
  };

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

      // Fetch summary table
    axios.get('http://localhost:5000/load_summary_table', {
       params: { working_directory: appState.working_directory },
     })
     .then(res => {
       setSummaryData(res.data);
     })
     .catch(console.error);
  }, [appState]);

  useEffect(() => {
    const tagSet = new Set(selectedTags.map(t => t.value));
    const adductSet = new Set(selectedAdducts.map(a => a.value));
    const grouped = {};
    compounds.forEach(row => {
      if (!row.ID) return;

      const rowTags = (typeof row.tag === 'string' ? row.tag : row.tag?.toString() || '').split(',').map(t => t.trim());
      const rowAdduct = row.adduct ? row.adduct.trim() : '';

      const tagMatch = selectedTags.length === 0 || rowTags.some(t => tagSet.has(t));
      const adductMatch = selectedAdducts.length === 0 || adductSet.has(rowAdduct);

      if (tagMatch && adductMatch) {
        if (!grouped[row.ID]) grouped[row.ID] = [];
        grouped[row.ID].push(row);
      }
    });
    const result = Object.entries(grouped).map(([id, group]) => ({ id, group }));

    setGroupedByID(result);
    const prevSelectedId = selectedIdRef.current || (compoundOptions[currentIndex]?.value);
    setCompoundOptions(result.map(entry => {
      const first = entry.group[0];
      const structureRow = entry.group.find(r => {
        const k = (r.known ?? '').toString().trim().toLowerCase();
        const hasName = r.Name && String(r.Name).trim().length > 0;
        return k === 'structure' && hasName;
      });
      const label =  structureRow
        ? `${entry.id} - ${String(structureRow.Name).trim()}`
        : `${entry.id} - ${Number(first?.mz ?? 0).toFixed(4)}`;
      return {
        value: entry.id,
        label
      };
    }));

    let newIndex = 0;
    if (prevSelectedId) {
      const idx = result.findIndex(e => e.id.toString() === prevSelectedId.toString());
      if (idx !== -1) newIndex = idx;
    }
   
    setCurrentIndex(newIndex);
     selectedIdRef.current = result[newIndex]?.id?.toString() || null;
  }, [compounds, selectedTags, selectedAdducts]);

  const extractUnique = (data, field) => {
    const set = new Set();
    data.forEach((row) => {
      const fieldValue = row[field];
      if (typeof fieldValue === 'string') {
        fieldValue.split(',').forEach((val) => {
          if (val.trim()) set.add(val.trim());
        });
      } else if (typeof fieldValue === 'number') {
        set.add(fieldValue.toString());
      }
      // else ignore null/undefined/other bad types
    });
    return Array.from(set).map((v) => ({ value: v, label: v }));
  };

  const handlePrev = () => setCurrentIndex((prev) => (prev > 0 ? prev - 1 : prev));
  const handleNext = () => setCurrentIndex((prev) => (prev < compoundOptions.length - 1 ? prev + 1 : prev));

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
    if (selected) {
      setSelectedGroup(selected.group);
      selectedIdRef.current = selected.id.toString();
      const flags = {};
      selected.group.forEach(row => {
        const key = `${row.ID}_${row.adduct}_${row.tag}`;
        const summaryMatch = summaryData.find(
           s => s.ID === row.ID && s.adduct === row.adduct && s.tag === row.tag
        ) || {};

        const cached = qaFlagsCache.current[key];
        flags[key] = cached ? { ...cached } : {
          MS1_Exists: isTrue(summaryMatch.qa_ms1_exists),
          MS2_Exists: isTrue(summaryMatch.qa_ms2_exists),
          MS1_Intensity: isTrue(summaryMatch.qa_ms1_good_int),
          S2N_ratio: isTrue(summaryMatch.qa_ms1_above_noise),
          RT_Alignment: isTrue(summaryMatch.alignment),
          adduct: row.adduct,
          tag: row.tag
        };
      });
      setQaFlags(flags);
    }
  }, [currentIndex, compoundOptions, groupedByID]);

  const toggleFlag = (key, flag) => {
  setQaFlags(prev => {
    const updated = {
      ...prev,
      [key]: {
        ...prev[key],
        [flag]: !prev[key][flag]
      }
    };
    qaFlagsCache.current[key] = updated[key];  // store it persistently
    return updated;
  });
};

const handleExportPeakList = async () => {
  if (!appState?.working_directory || !selectedGroup || !isSingleTagSelected()) return;

  try {
    const { ID, adduct, tag } = selectedGroup[0];
    const summaryRow = summaryData.find(
      (r) => r.ID.toString() === ID.toString() && r.adduct === adduct && r.tag === tag
    );

    if (!summaryRow?.ms2_rt) {
      setToastMessage('⚠️ No MS2 scan available.');
      setTimeout(() => setToastMessage(''), 3000);
      return;
    }

    const ms2Rt = parseFloat(summaryRow.ms2_rt);
    console.log('MS2 RT:', ms2Rt);  // Log MS2 RT value

    // Make the API call
    const res = await axios.get('http://localhost:5000/get_csv', {
      params: {
        working_directory: appState.working_directory,
        compound_id: ID,
        tag,
        adduct,
        type: 'MS2'
      }
    });

    // Log the API response
    console.log('API Response:', res.data);  // Log the full response data

    const csvText = res.data;
    if (!csvText) {
      setToastMessage('⚠️ No CSV data returned.');
      setTimeout(() => setToastMessage(''), 3000);
      return;
    }

    const lines = csvText.trim().split('\n');
    const headers = lines[0].split(',');
    const rtIdx = headers.indexOf('ms2_rt');
    const peakIdx = headers.indexOf('peak_list');

    let closestLine = null;
    let minDiff = Infinity;

    for (let i = 1; i < lines.length; i++) {
      const row = lines[i].split(',');
      const rt = parseFloat(row[rtIdx]);
      const diff = Math.abs(rt - ms2Rt);
      if (diff < minDiff) {
        minDiff = diff;
        closestLine = row;
      }
    }

    if (!closestLine || !closestLine[peakIdx]) {
      setToastMessage('⚠️ No MS2 peak list found.');
      setTimeout(() => setToastMessage(''), 3000);
      return;
    }

    const peakString = closestLine[peakIdx];
    const formatted = peakString
      .split(';')
      .map((p) => {
        const [mz, intensity] = p.split(':');
        return `${mz}\t${intensity}`;
      })
      .join('\n');

    await navigator.clipboard.writeText(formatted);
    setToastMessage('✅ MS2 peak list copied to clipboard');
    setTimeout(() => setToastMessage(''), 3000);
  } catch (err) {
    console.error('Error in export:', err);  // Log the error
    setToastMessage('❌ Failed to export MS2 peak list.');
    setTimeout(() => setToastMessage(''), 3000);
  }
};

  
  const handleSaveSinglePlot = () => {
    const groupToUse = selectedGroup || groupedByID[currentIndex]?.group || [];
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
    try {
      const blob = await exportSummaryPDF(compoundsToSend, appState.working_directory);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", `summary_export.pdf`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      alert("Something went wrong while exporting the summary PDF.");
    }
  };

  const thStyle = { padding: '6px', border: `1px solid ${theme.border}`, textAlign: 'left', fontWeight: '600', color: theme.text, background: theme.tableHeader };
  const tdStyle = { padding: '6px', border: `1px solid ${theme.border}`, color: theme.text };
  const plotButtonStyle = {
    padding: '6px 12px', fontSize: '12px', fontWeight: '600', borderRadius: '5px',
    background: `linear-gradient(to bottom, ${theme.btnGradFrom}, ${theme.btnGradTo})`, color: theme.accentText,
    boxShadow: '0 2px 5px rgba(0,0,0,0.1)', cursor: 'pointer', border: `1px solid ${theme.border}`
  };

  const exportPeakListButtonStyle = { // Missing definition for exportPeakListButtonStyle
    background: `linear-gradient(to bottom, ${theme.btnGradFrom}, ${theme.btnGradTo})`,
    color: theme.accentText,
    border: `1px solid ${theme.border}`,
    borderRadius: 5,
    padding: '6px 12px'
  };

  
  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', background: theme.bg, color: theme.text }}>
      <div style={{ padding: '12px', backgroundColor: theme.panelLite, borderBottom: `1px solid ${theme.border}`, fontWeight: 'bold', fontSize: '18px', textAlign: 'center' }}>
         pyMSscreen Visualization Dashboard
      </div>
      
      {/* Plotting Help (collapsible) */}
      <div style={{ padding: '8px 16px', textAlign: 'center', maxWidth: '90%', margin: '0 auto' }}>
        <details style={{ background: theme.helpBg, padding: 10, borderRadius: 8, border: `1px solid ${theme.helpBorder}`, color: theme.text }}>
          <summary style={{ cursor: 'pointer', fontWeight: 'bold' }}>
            ℹ️ Plotting Page info
          </summary>
          <ul style={{ paddingLeft: 20, marginTop: 10, textAlign: 'left' }}>
            <li><strong>Default grouping:</strong> plots are grouped by <em>all</em> tags and adducts. Use Tag/Adduct filters to change the grouping.</li>
            <li><strong>Top EICs:</strong> the top <em>3 most intense</em> EIC traces are shown. Double-click a legend item to isolate its trace. Selecting the corresponding legend shows the <em>MS2 peak</em> line (if present).</li>
            <li><strong>Relative intensity:</strong> toggles MS2/fragment axes between relative and absolute scales.</li>
            <li><strong>Greyscale fragments:</strong> renders MS2 fragment sticks in greyscale.</li>
            <li><strong>EIC colour fill:</strong> fills the EIC peak under the line.</li>
            <li><strong>Publication mode:</strong> report-friendly styles; use the plot toolbar to download <em>SVG</em> or <em>PNG</em>.</li>
          </ul>
        </details>
      </div>
        
      <div style={{ display: 'flex', flex: 1 }}>
        <div style={{ width: '340px', padding: '16px', overflow: 'auto', background: theme.leftPane, borderRight: `2px solid ${theme.leftPaneBorder}`, display: 'flex', flexDirection: 'column', color: theme.text }}>
          <h3 style={{ textAlign: 'center' }}>Settings Pane</h3>

      {/* Settings Pane Help (collapsible) */}
      <div style={{ margin: '8px 0' }}>
        <details style={{ background: theme.helpBg, padding: 10, borderRadius: 8, border: `1px solid ${theme.helpBorder}`, color: theme.text }}>
          <summary style={{ cursor: 'pointer', fontWeight: 'bold' }}>
             Settings Pane info
          </summary>
          <ul style={{ paddingLeft: 20, marginTop: 10 }}>
            <li><strong>Filter by Tag/Adduct:</strong> narrow the plotted group. Clearing filters returns to the full group.</li>
            <li><strong>Save Plot:</strong> saves the current compound’s combined plot (format choice via the plot toolbar, not this button).</li>
            <li><strong>Export Summary PDF:</strong> creates a quick visual overview of <em>all</em> grouped compounds.</li>
            <li><strong>Export Peak List:</strong> enabled when exactly one Tag is selected; copies MS2 peaks for tools like <em>MetFrag</em>.</li>
          </ul>
        </details>
      </div>

          <label>Filter by Tag:</label>
          <Select isMulti options={tagOptions} onChange={setSelectedTags} styles={selectStyles} />

          <label style={{ marginTop: '10px' }}>Filter by Adduct:</label>
          <Select isMulti options={adductOptions} onChange={setSelectedAdducts} styles={selectStyles} />

          <label style={{ marginTop: '10px' }}>Select Compound:</label>
          <Select
            options={compoundOptions}
            styles={selectStyles}
            value={compoundOptions[currentIndex] || null}
            onChange={(selected) => {
              const index = compoundOptions.findIndex(opt => opt.value === selected.value);
              if (index !== -1) {
              setCurrentIndex(index);
              selectedIdRef.current = selected.value;
              }
            }}
          />

          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '8px' }}>
            <button onClick={handlePrev} style={plotButtonStyle}>Previous</button>
            <button onClick={handleNext} style={plotButtonStyle}>Next</button>
          </div>

         {/* Manual QA Flags (header pinned; table scrolls) */}
<div
  style={{
    marginTop: '12px',
    border: `1px solid ${theme.border}`,
    borderRadius: '8px',
    background: theme.panel,
    color: theme.text,
    display: 'flex',
    flexDirection: 'column'
  }}
>
  <div
    style={{
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      padding: '8px 10px',
      borderBottom: `1px solid ${theme.border}`,
      background: theme.panelLite, 
      color: theme.text
    }}
  >
    <h4 style={{ fontSize: '13px', margin: 0 }}>Manual QA Flags</h4>
    <button
      onClick={handleUpdateQA}
      style={{ ...plotButtonStyle, fontSize: '11px', padding: '4px 10px', borderRadius: 5 }}
    >
      ✅ Update Summary Table
    </button>
  </div>

  <div style={{ maxHeight: '230px', overflow: 'auto', padding: '8px' }}>
    {selectedGroup && selectedGroup.length > 0 ? (
      <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
        <thead>
          <tr>
            <th style={thStyle}>Tag</th>
            <th style={thStyle}>Adduct</th>
            <th style={thStyle}>MS1 Exists</th>
            <th style={thStyle}>MS2 Exists</th>
            <th style={thStyle}>MS1 Intensity</th>
            <th style={thStyle}>S2N Ratio</th>
            <th style={thStyle}>RT Align</th>
          </tr>
        </thead>
        <tbody>
          {(selectedGroup || []).map((row, idx) => {
            const key = `${row.ID}_${row.adduct}_${row.tag}`;
            const flags = qaFlags[key] || {};
            return (
              <tr key={idx}>
                <td style={tdStyle}>{row.tag}</td>
                <td style={tdStyle}>{row.adduct}</td>
                {['MS1_Exists','MS2_Exists','MS1_Intensity','S2N_ratio','RT_Alignment'].map(flag => (
                  <td key={flag} style={{ ...tdStyle, textAlign: 'center' }}>
                    <input
                      type="checkbox"
                      checked={!!flags[flag]}
                      onChange={() => toggleFlag(key, flag)}
                      style={checkboxStyle}
                    />
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    ) : (
      <div style={{ textAlign: 'center', color: '#666', fontSize: 12, padding: 6 }}>
        No compound selected
      </div>
    )}
  </div>
</div>

{/* Grouped Entries (single instance below QA flags) */}
{selectedGroup && (
  <div
    style={{
      background: theme.panel, 
      color: theme.text,
      padding: '12px',
      borderRadius: '12px',
      marginTop: '12px',
      boxShadow: '0 2px 5px rgba(0,0,0,0.1)',
      border: `1px solid ${theme.border}`
    }}
  >
    <h4 style={{ textAlign: 'center', fontSize: 14, marginBottom: 10 }}>Grouped Entries</h4>
    <table
      style={{
        width: '100%',
        fontSize: 12,
        borderCollapse: 'separate',
        borderSpacing: '0 4px'
      }}
    >
      <thead style={{ backgroundColor: theme.tableHeader }}>
        <tr>
          <th style={thStyle}>Tag</th>
          <th style={thStyle}>Adduct</th>
          <th style={thStyle}>{selectedGroup[0]?.known === 'suspect' ? 'm/z' : 'Name'}</th>
        </tr>
      </thead>
      <tbody>
        {selectedGroup.map((row, idx) => (
          <tr key={idx} style={{ backgroundColor: idx % 2 === 0 ? theme.tableRowA : theme.tableRowB, color: theme.text }}>
            <td style={tdStyle}>{row.tag}</td>
            <td style={tdStyle}>{row.adduct}</td>
            <td style={tdStyle}>
              {selectedGroup[0]?.known === 'suspect' ? parseFloat(row.mz).toFixed(4) : row.Name}
            </td>
          </tr>
        ))}
      </tbody>
    </table>

    <button
      onClick={() => setSelectedGroup(groupedByID[currentIndex]?.group)}
      style={{
        marginTop: 10, width: '100%', padding: 8, borderRadius: 6, fontWeight: 'bold',
        fontSize: 13, background: 'linear-gradient(to right, #a7cce5, #bfe1f2)', color: theme.text,
        border: `1px solid ${theme.border}`, cursor: 'pointer'
      }}
    >
      📊 Plot Selected
    </button>

    <button
      onClick={handleSaveSinglePlot}
      style={{
        padding: 8, marginTop: 10, borderRadius: 6,
        background: `linear-gradient(to bottom, ${theme.btnGradFrom}, ${theme.btnGradTo})`,
        color: theme.accentText,
        border: `1px solid ${theme.border}`, color: theme.text, fontWeight: 'bold', cursor: 'pointer', width: '100%'
      }}
    >
      💾 Save Plot
    </button>

    <button
      onClick={handleExportSummaryPDF}
      style={{
        padding: 8, marginTop: 10, borderRadius: 6,
        background: `linear-gradient(to bottom, ${theme.btnGradFrom}, ${theme.btnGradTo})`,
        border: `1px solid ${theme.border}`, color: theme.text, fontWeight: 'bold', cursor: 'pointer', width: '100%',
      }}
    >
      📝 Export Summary PDF
    </button>

    <button
      onClick={handleExportPeakList}
      disabled={!isSingleTagSelected()}
      style={{
        ...exportPeakListButtonStyle,
        marginTop: 10,
        width: '100%',
        opacity: isSingleTagSelected() ? 1 : 0.5,
        cursor: isSingleTagSelected() ? 'pointer' : 'not-allowed'
      }}
      title={
        isSingleTagSelected()
          ? 'Copy MS2 peak list to clipboard'
          : 'Select a single tag to enable MS2 export'
      }
    >
      📋 Export Peak List
    </button>
  </div>
)}

<button
  onClick={() => navigate('/')}
  style={{
    marginTop: '12px',
    padding: '6px 12px',
    fontSize: '12px',
    fontWeight: 600,
    borderRadius: 5,
    background: `linear-gradient(to bottom, ${theme.btnGradFrom}, ${theme.btnGradTo})`,
    color:  theme.text,
    boxShadow: '0 2px 5px rgba(0,0,0,0.1)',
    cursor: 'pointer'
  }}
>
  Back to Setup
</button>
</div> {/* ← close LEFT pane */}

<div style={{ flex: 1, padding: '16px', overflowY: 'auto' }}>
  <CompoundPlot
    compoundGroup={selectedGroup || []}
    onExportReady={setExportPayload}
    onFilenameChange={setSinglePlotFilename}
    theme={theme}
  />
</div>
</div> {/* ← close the flex container (left + right) */}

{/* Global toast (one place only) */}
{toastMessage && (
  <div
    style={{
      position: 'fixed',
      bottom: 20,
      left: '50%',
      transform: 'translateX(-50%)',
      backgroundColor: theme.toastBg,
      color: theme.toastText,
      padding: '10px 20px',
      borderRadius: 5,
      fontSize: 14,
      boxShadow: '0 2px 5px rgba(0,0,0,0.2)',
      zIndex: 1000,
      border: `1px solid ${theme.border}`
    }}
  >
    {toastMessage}
  </div>
 )}
</div> 
);
};



export default PlottingPage;
