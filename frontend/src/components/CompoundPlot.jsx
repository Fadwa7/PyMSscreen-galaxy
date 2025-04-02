
import React, { useEffect, useState } from 'react';
import Plot from 'react-plotly.js';
import Papa from 'papaparse';
import axios from 'axios';
import { useAppState } from '../context/AppStateContext';
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

  useEffect(() => {
    const fetchData = async () => {
      if (!compoundGroup?.length || !appState?.working_directory) return;

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
          const closestMS2 = ms2Data.reduce((a, b) => {
            return Math.abs(parseFloat(a.ms2_rt) - ms1RT) < Math.abs(parseFloat(b.ms2_rt) - ms1RT) ? a : b;
          });

          const intensity = parseFloat(closestMS2.ms2_intensity);
          const yClosest = useRelative ? [0, 1] : [0, intensity];

          const identifier = `${tag}_${adduct}`;
          const color = colors[uniqueIds.indexOf(identifier)];
            data.push({
            x: [closestMS2.ms2_rt, closestMS2.ms2_rt],
            y: yClosest,
            mode: 'lines',
            name: `MS2 Peak | ${tag} | ${compoundId}`,
            line: { dash: 'dash', color: color, width: 2 },
            xaxis: 'x2',
            yaxis: 'y2',
            showlegend: true
          });

          const peaks = parsePeakList(closestMS2.peak_list);
          const maxY = Math.max(...peaks.map(p => p.y));
          if (!useRelative) maxFragmentY = Math.max(maxFragmentY, ...peaks.map(p => p.y));

          peaks.forEach(p => {
            const yVal = useRelative ? p.y / maxY : p.y;
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

      const layout = {
        height: 1200,
        width: 1000,
        margin: { l: 80, r: 60, t: 40, b: 50 },
        grid: { rows: 3, columns: 1, pattern: 'independent', roworder: 'top to bottom' },
        title: { text: 'Mass Spectra Overview' },
        showlegend: true,
        xaxis: { title: 'RT (min)', range: [0, 30], anchor: 'y1' },
        yaxis: { title: { text: 'MS1 Intensity' }, tickformat: '.2e', anchor: 'x1' },
        xaxis2: { title: 'RT (min)', range: [0, 30], anchor: 'y2' },
        yaxis2: {
          title: { text: 'MS2 Intensity' },
          range: useRelative ? [0, 1.05] : [0, maxMS1Y * 1.1],
          tickformat: useRelative ? '' : '.2e',
          anchor: 'x2'
        },
        xaxis3: { title: 'm/z', anchor: 'y3' },
        yaxis3: {
          title: { text: 'Fragment Intensity' },
          range: useRelative ? [0, 1.05] : [0, maxFragmentY * 1.1],
          tickformat: useRelative ? '' : '.2e',
          anchor: 'x3'
        }
      };

      setPlotObj({ data, layout });

      if (onExportReady && match?.SMILES) {
        const smilesUrl = `https://cactus.nci.nih.gov/chemical/structure/${encodeURIComponent(match.SMILES)}/image?height=180&width=180`;
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

      {structureInfo?.smiles && (
        <div style={{ alignSelf: 'center', width: '220px', padding: '0.5rem', backgroundColor: 'white', border: '1px solid #D1D5DB', borderRadius: '0.5rem', boxShadow: '0 1px 3px rgba(0,0,0,0.1)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
          <img
            src={`https://cactus.nci.nih.gov/chemical/structure/${encodeURIComponent(structureInfo.smiles)}/image?height=180&width=180`}
            alt="Structure"
            title={`Compound: ${structureInfo.name}
SMILES: ${structureInfo.smiles}`}
            style={{ width: '180px', height: '180px', objectFit: 'contain', border: '1px solid #E5E7EB', borderRadius: '0.25rem' }}
          />
          <a
            href={`https://cactus.nci.nih.gov/chemical/structure/${encodeURIComponent(structureInfo.smiles)}/image?height=1024&width=1024`}
            download={`${structureInfo.name || 'structure'}.png`}
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
