import React, { useEffect, useState } from 'react';
import Plot from 'react-plotly.js';
import Papa from 'papaparse';
import axios from 'axios';
import { useAppState } from '../context/AppStateContext';
import { loadExtractionConfig, saveExtractConfig } from '../api/api';
import chroma from 'chroma-js';

const parsePeakList = (peakStr) => {
  return peakStr.split(';').map((pair) => {
    const [mz, intensity] = pair.split(':').map(Number);
    return { x: mz, y: intensity };
  }).filter(p => !isNaN(p.x) && !isNaN(p.y));
};

const encodeParam = (value) => encodeURIComponent(value);

const loadCSV = async (compoundId, type, tag, adduct, workingDir) => {
  const params = new URLSearchParams({
    working_directory: workingDir,
    compound_id: compoundId,
    type,
    tag,
    adduct: encodeParam(adduct),
  });
  try {
    const res = await axios.get(`http://localhost:5000/get_csv?${params}`);
    return new Promise((resolve) => {
      Papa.parse(res.data, {
        header: true,
        skipEmptyLines: true,
        complete: (results) => resolve(results.data),
      });
    });
  } catch {
    return [];
  }
};

const loadComprehensiveTable = async (workingDir) => {
  const params = new URLSearchParams({ working_directory: workingDir });
  try {
    const res = await axios.get('http://localhost:5000/load_comprehensive_table', { params });
    return res.data;
  } catch {
    return [];
  }
};

const handleHighRes = (smiles, compoundName) => {
  if (!smiles) return;  // Ensure SMILES string is provided

  // Construct high-res image URL using simolecule.com/cdkdepict
  const highResUrl = `https://cactus.nci.nih.gov/chemical/structure/${encodeURIComponent(smiles)}/image?height=1024&width=1024&title=${encodeURIComponent(compoundName || 'Unknown Compound')}`;

  // Log the URL to the console for debugging
  console.log("High-Resolution URL:", highResUrl);

  // Open a new popup window
  const popupWindow = window.open('', '_blank', 'width=800,height=800,scrollbars=yes,resizable=yes');

  // Add content to the popup window
  popupWindow.document.write(`
    <html>
      <head>
        <title>High-Resolution Image</title>
        <style>
          body {
            text-align: center;
            padding: 20px;
            font-family: Arial, sans-serif;
            margin: 0;
            background-color: #f4f4f4;
          }
          h1 {
            margin-bottom: 20px;
            font-size: 20px;
            color: #333;
          }
          img {
            max-width: 100%;
            max-height: 80vh;
            border: 1px solid #ccc;
            margin-bottom: 20px;
          }
          button {
            padding: 10px 20px;
            font-size: 16px;
            background-color: #4CAF50;
            color: white;
            border: none;
            cursor: pointer;
            border-radius: 5px;
          }
          button:hover {
            background-color: #45a049;
          }
        </style>
      </head>
      <body>
        <h1>${compoundName || 'Unknown Compound'}</h1>
        <img src="${highResUrl}" alt="High-Resolution Structure" />
        <br />
        <button onclick="window.close();">Close</button>
      </body>
    </html>
  `);
};

const CompoundPlot = ({ compoundGroup, onExportReady }) => {
  const handleExportSummary = async () => {
    console.log("🚀 Calling exportSummaryPDF with:", compoundGroup, appState.working_directory);
    try {
      const blob = await exportSummaryPDF(compoundGroup, appState.working_directory);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", "summary_report.pdf");
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Export error:", err);
      alert("Failed to export PDF.");
    }
  };


  const [useRelative, setUseRelative] = useState(true);
  const { appState } = useAppState();
  const [plotObj, setPlotObj] = useState(null);
  const [structureInfo, setStructureInfo] = useState(null);
  const [mzText, setMzText] = useState('');

  useEffect(() => {
    const fetchData = async () => {
      if (!compoundGroup?.length || !appState?.working_directory) return;
      
      const retTimeShiftTol = await loadExtractionConfig(appState.working_directory);
      let data = [];
      let maxMS1Y = 0;
      let maxFragmentY = 0;

      const compTable = await loadComprehensiveTable(appState.working_directory);
      const first = compoundGroup[0];
      const match = compTable.find(r => r.ID === first.ID);
      if (match) setStructureInfo({ smiles: match.SMILES, name: match.Name });

      const identifiers = compoundGroup.map(c => `${c.tag}_${c.adduct}`);
      const uniqueIds = Array.from(new Set(identifiers));
      const colors = chroma.scale('Set1').colors(uniqueIds.length);

      for (const compound of compoundGroup) {
        const { ID, tag, adduct } = compound;
        const compoundId = ID;

        const ms1Data = await loadCSV(compoundId, 'EIC', tag, adduct, appState.working_directory);
        const ms2Data = await loadCSV(compoundId, 'MS2', tag, adduct, appState.working_directory);

        let ms1RT = 'N/A';
        if (ms1Data.length) {
          const maxMS1 = ms1Data.reduce((a, b) => parseFloat(a.intensity) > parseFloat(b.intensity) ? a : b);
          ms1RT = parseFloat(maxMS1.rt);
          const intensities = ms1Data.map(row => parseFloat(row.intensity));
          maxMS1Y = Math.max(maxMS1Y, ...intensities);

          data.push({
            x: ms1Data.map(row => parseFloat(row.rt)),
            y: intensities,
            mode: 'lines',
            name: `MS1 | ${tag} | RT: ${ms1RT.toFixed(2)} | ${adduct} | ${compoundId}`,
            xaxis: 'x1',
            yaxis: 'y1',
            showlegend: true
          });
        }

        if (ms2Data.length && ms1RT !== 'N/A') {
          const candidates = ms2Data.filter(m => Math.abs(parseFloat(m.ms2_rt) - ms1RT) <= retTimeShiftTol);
          if (candidates.length) {
            const closestMS2 = candidates.reduce((a, b) => (
              Math.abs(parseFloat(a.ms2_rt) - ms1RT) < Math.abs(parseFloat(b.ms2_rt) - ms1RT) ? a : b
            ));

          const identifier = `${tag}_${adduct}`;
          const color = colors[uniqueIds.indexOf(identifier)];

          data.push({
            x: [parseFloat(closestMS2.ms2_rt), parseFloat(closestMS2.ms2_rt)],
            y: useRelative ? [0, 1050] : [0, maxMS1Y * 1.1],
            mode: 'lines',
            name: `MS2 Peak | ${tag} | RT: ${parseFloat(closestMS2.ms2_rt).toFixed(2)} | ${adduct} | ${compoundId}`,
            line: { dash: 'dash', color: color, width: 2 },
            xaxis: 'x2',
            yaxis: 'y2',
            showlegend: true
          });

          const peaks = parsePeakList(closestMS2.peak_list);
          if (peaks.length) {
            const maxY = Math.max(...peaks.map(p => p.y));
            maxFragmentY = useRelative ? 1050 : Math.max(maxFragmentY, maxY);

          peaks.forEach(p => {
            const yVal = useRelative ? p.y / maxY * 1050 : p.y;
            data.push({
              x: [p.x, p.x],
              y: [0, yVal],
              mode: 'lines',
              type: 'scatter',
              line: { width: 2 },
              name: `Frag | ${tag} | ${compoundId}`,
              showlegend: false,
              xaxis: 'x3',
              yaxis: 'y3'
            });
          });

          data.push({
            x: [],
            y: [],
            mode: 'lines',
            type: 'scatter',
            name: `Fragments | ${compoundId}`,
            line: { color: 'transparent' },
            showlegend: true,
            xaxis: 'x3',
            yaxis: 'y3'
          });
         }
        }
       }
      }

      const layout = {
        height: 1200,
        width: 1000,
        margin: { l: 80, r: 60, t: 40, b: 50 },
        grid: { rows: 3, columns: 1, pattern: 'independent', roworder: 'top to bottom' },
        title: {
          text: first.known === "suspect"
            ? `Mass Spectra Overview — m/z: ${parseFloat(first.mz).toFixed(4)}`
            : `Mass Spectra Overview — Name: ${first.Name} | m/z: ${parseFloat(first.mz).toFixed(4)}`,
          xanchor: 'left',
          x: 0
        },     
        showlegend: true,
        xaxis: { title:{ text: 'RT (min)'}, range: [0, 30], anchor: 'y1' },
        yaxis: { title: { text: 'MS1 Intensity' }, tickformat: '.2e', anchor: 'x1' },
        xaxis2: { title:{ text: 'RT (min)'}, range: [0, 30], anchor: 'y2' },
        yaxis2: {
          title: { text: 'MS2 Intensity' },
          range: useRelative ? [0, 1050] : [0, maxMS1Y * 1.1],
          tickformat: useRelative ? '' : '.2e',
          anchor: 'x2'
        },
        xaxis3: { title: 'm/z', anchor: 'y3' },
        yaxis3: {
          title: { text: 'Fragment Intensity' },
          range: useRelative ? [0, 1050] : [0, maxFragmentY * 1.1],
          tickformat: useRelative ? '' : '.2e',
          anchor: 'x3'
        }
      };

      setPlotObj({ data, layout });
      setMzText(`Name: ${first.Name} | m/z: ${parseFloat(first.mz).toFixed(4)}`);

      if (onExportReady && match?.SMILES) {
        const smilesUrl = `https://cactus.nci.nih.gov/chemical/structure/${encodeURIComponent(match.SMILES)}/image?height=180&width=180&title=${encodeURIComponent(match.Name || 'Unknown')}`;
        onExportReady({ plots: [{ id: 'stackedPlot', data, layout }], smilesUrl });
      }
    };

    fetchData();
  }, [compoundGroup, appState, useRelative, onExportReady]);


  return (
    <div style={{ display: 'flex', flexDirection: 'column', width: '100%', height: '100%', overflowY: 'auto', padding: '1rem', gap: '1.5rem' }}>
      <div style={{ display: 'flex', justifyContent: 'flex-end', paddingRight: '1rem', gap: '0.5rem', alignItems: 'center' }}>
        <label style={{ display: 'flex', gap: '0.25rem', fontSize: '0.875rem', color: '#374151', alignItems: 'center' }}>
          <input
            type="checkbox"
            checked={useRelative}
            onChange={(e) => setUseRelative(e.target.checked)}
          />
          Relative Intensity (MS2/Fragments)
        </label>
      </div>

      {plotObj ? (
        <Plot
          data={plotObj.data}
          layout={plotObj.layout}
          style={{ width: '100%', height: '100%' }}
          config={{ responsive: true }}
        />
      ) : (
        <div style={{ color: '#6B7280', fontStyle: 'italic', textAlign: 'center', marginTop: '2.5rem' }}>
          🧪 Click 'Plot' to generate visualizations.
        </div>
      )}

      {/* Copyable Name and m/z */}
      <div
        style={{
          marginTop: '12px',
          padding: '8px',
          background: '#f7f7f7',
          border: '1px solid #ccc',
          borderRadius: '6px',
          fontFamily: 'monospace',
          fontSize: '13px',
          userSelect: 'text',
        }}
      >
        {mzText}
      </div>

      {structureInfo?.smiles && (
        <div style={{ alignSelf: 'center', width: '220px', padding: '0.5rem', backgroundColor: 'white', border: '1px solid #D1D5DB', borderRadius: '0.5rem', boxShadow: '0 1px 3px rgba(0,0,0,0.1)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
          <img
            src={`https://cactus.nci.nih.gov/chemical/structure/${encodeURIComponent(structureInfo.smiles)}/image?width=180&height=180`}
            alt="Structure"
            title={`Compound: ${structureInfo.name}\nSMILES: ${structureInfo.smiles}`}
            style={{ width: '180px', height: '180px', objectFit: 'contain', border: '1px solid #E5E7EB', borderRadius: '0.25rem' }}
          />
          <a
            href={`#`}
            onClick={() => handleHighRes(structureInfo.smiles, structureInfo.name)}
            style={{ fontSize: '0.75rem', color: '#2563EB', marginTop: '0.5rem', textDecoration: 'underline', textAlign: 'center' }}
          >
            ⬇ High-Res
          </a>
        </div>
      )}
    </div>
  );
};

export default CompoundPlot;
