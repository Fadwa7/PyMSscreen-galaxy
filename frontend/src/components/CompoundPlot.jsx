/**
 * @typedef {Object} EICRow
 * @property {string|number} rt - Retention time (minutes).
 * @property {string|number} intensity - MS1 intensity.
 */

/**
 * @typedef {Object} MS2Row
 * @property {string|number} ms2_rt - MS2 retention time (minutes).
 * @property {string|number} ms2_intensity - Total MS2 intensity.
 * @property {string} peak_list - Semicolon-separated "m/z:intensity" fragment list.
 */

/**
 * @typedef {Object} CompoundPlotRow
 * @property {string} ID - Compound identifier.
 * @property {string} tag - Tag associated with the mzML file.
 * @property {string} adduct - Adduct used for m/z calculation.
 * @property {string} SMILES - SMILES representation of the compound.
 * @property {string} Name - Compound name.
 * @property {EICRow[]} [eicData] - Extracted ion chromatogram data.
 * @property {MS2Row[]} [ms2Data] - Extracted MS2 spectra data.
 */

/**
 * @typedef {Object} PlotExportPayload
 * @property {Array<{id: string, data: Object[], layout: Object}>} plots
 */

/**
 * @file CompoundPlot.jsx
 * @summary Plotly-based visualization of MS1 EICs, MS2 precursor peaks, and fragment spectra.
 *
 * @description
 * This component renders a stacked, three-panel visualization for a selected compound:
 * 1) MS1 extracted ion chromatogram (EIC)
 * 2) MS2 precursor peak aligned to the MS1 apex
 * 3) MS2 fragment ion spectrum
 *
 * Data are grouped by compound ID and rendered per tag/adduct combination.
 * The component supports absolute and relative intensity scaling for MS2
 * and fragment spectra.
 *
 * Export-ready plot objects are emitted to the parent component for saving
 * or PDF generation.
 */

import React, { useEffect, useState, useMemo, useRef } from 'react';
import Plot from 'react-plotly.js';
import Papa from 'papaparse';
import axios from 'axios';
import { useAppState } from '../context/AppStateContext';
import { loadExtractionConfig, API_BASE} from '../api/api';
import chroma from 'chroma-js';
import Plotly from 'plotly.js-dist-min';

// === Tag-based color controls (scales automatically) ===
// 1) Optional explicit overrides per TAG (user can fill these)
export const TAG_COLOR_OVERRIDES = {
// e.g. 'Pos': '#B22222', 'Neg': '#1F77B4'
};
// 2) Base palette used for the first N unique tags
const BASE_TAG_PALETTE = [
'#B22222', // deep red
'#1F77B4', // blue
'#E69F00', // orange/gold
'#2CA02C', // green
'#9467BD', // purple
'#17BECF', // teal
'#E377C2', // pink
'#8C564B', // brown
'#7F7F7F', // gray
];
// 3) Deterministic fallback for unlimited tags: hash tag → hue on HSL wheel
const hashString = (s) => {
let h = 0;
for (let i = 0; i < s.length; i++) { h = (h << 5) - h + s.charCodeAt(i); h |= 0; }
return Math.abs(h);
};
export const getTagColor = (tag, uniqueTags) => {
if (TAG_COLOR_OVERRIDES[tag]) return TAG_COLOR_OVERRIDES[tag];
const idx = uniqueTags.indexOf(tag);
if (idx > -1 && idx < BASE_TAG_PALETTE.length) return BASE_TAG_PALETTE[idx];
const hue = hashString(tag) % 360; // stable per tag
return chroma.hsl(hue, 0.62, 0.52).hex();
};


/**
 * Parse a semicolon-separated MS2 fragment peak list.
 *
 * @function parsePeakList
 * @param {string} peakStr
 * Fragment list encoded as "m/z:intensity;m/z:intensity;..."
 *
 * @returns {{x: number, y: number}[]}
 * Parsed fragment peaks suitable for Plotly rendering.
 *
 * @remarks
 * Invalid or non-numeric entries are filtered out.
 */

const parsePeakList = (peakStr) => {
  return peakStr.split(';').map((pair) => {
    const [mz, intensity] = pair.split(':').map(Number);
    return { x: mz, y: intensity };
  }).filter(p => !isNaN(p.x) && !isNaN(p.y));
};

const loadCSV = async (compoundId, type, tag, adduct, workingDir) => {
  const safeAdduct =
    adduct === null || adduct === undefined || adduct === 'null' ? '' : adduct;
  const params = new URLSearchParams({
    working_directory: workingDir,
    compound_id: compoundId,
    type,
    tag,
    adduct: safeAdduct,
  });
  try {
    const res = await axios.get(`${API_BASE}/get_csv?${params}`);
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
    const res = await axios.get(`${API_BASE}/load_comprehensive_table`, { params });
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

export function movingAverage(arr, window = 5) {
if (window < 2) return arr.slice();
const half = Math.floor(window / 2);
const out = new Array(arr.length).fill(0);
for (let i = 0; i < arr.length; i++) {
const start = Math.max(0, i - half);
const end = Math.min(arr.length - 1, i + half);
let sum = 0;
let count = 0;
for (let j = start; j <= end; j++) {
sum += arr[j];
count++;
}
out[i] = sum / count;
}
return out;
}


export function findTopPeaks(rtArr, intArr, {
n = 3,
minSeparation = 0.15,
prominenceFrac = 0.05,
minWidthPoints = 3,
minSignalPoints = 3,
signalFrac = 0.1,
} = {}) {
// Keep identical to find_top_peaks() in backend extract_prescreen_mspgen.py.
if (!rtArr?.length || rtArr.length !== intArr.length) return [];
const sm = movingAverage(intArr, 5);
const maxI = Math.max(...sm);
if (!isFinite(maxI) || maxI <= 0) return [];
const minProm = maxI * prominenceFrac;


const candidates = [];
for (let i = 1; i < sm.length - 1; i++) {
if (sm[i] > sm[i - 1] && sm[i] >= sm[i + 1]) {
let l = i - 1;
while (l > 0 && sm[l] < sm[l + 1]) l--;
let r = i + 1;
while (r < sm.length - 1 && sm[r] < sm[r - 1]) r++;
const width = r - l;
if (width < minWidthPoints) continue;
const baseline = Math.max(Math.min(sm[l], sm[r]), 1e-12);
const prom = sm[i] - baseline;
if (prom >= minProm) {
// whole peak: walk downhill (or flat) on the smoothed trace to each valley
let a = i;
while (a > 0 && sm[a - 1] <= sm[a]) a--;
let b = i;
while (b < sm.length - 1 && sm[b + 1] <= sm[b]) b++;
// highest and lowest raw point of the peak region
let k = a;
let lo = intArr[a];
for (let j = a; j <= b; j++) {
if (intArr[j] > intArr[k]) k = j;
if (intArr[j] < lo) lo = intArr[j];
}
// a real peak rises clearly above its background in several scans;
// single-scan spikes and isolated points are not peaks
const level = lo + signalFrac * (intArr[k] - lo);
let signalPoints = 0;
for (let j = a; j <= b; j++) if (intArr[j] > level) signalPoints++;
if (signalPoints < minSignalPoints) continue;
// mark the peak at its highest raw point (never at a zero next to the peak)
candidates.push({ idx: k, rt: Number(rtArr[k]), intensity: intArr[k], smVal: sm[i], prom });
}
}
}


candidates.sort((a, b) => b.intensity - a.intensity);
const picked = [];
for (const c of candidates) {
if (picked.every((p) => Math.abs(p.rt - c.rt) >= minSeparation)) {
picked.push(c);
if (picked.length === n) break;
}
}
return picked.map(({ rt, intensity, idx }) => ({ rt, intensity, idx }));
}

// --- publication style constants
const PUB = {
  fontFamily: 'Arial, Helvetica, sans-serif',
  titleSize: 18,
  axisLabelSize: 14,
  tickSize: 12,
  legendSize: 12,
  lineWidth: 2.5,
  markerSize: 8,
  grid: '#E6E6E6'
};

// Distinct markers & dashes for tags (works in grayscale)
const TAG_MARKERS = ['circle', 'square', 'diamond', 'triangle-up', 'x', 'cross', 'triangle-down', 'star'];
const TAG_DASHES  = ['solid', 'dash', 'dot', 'dashdot', 'longdash', 'longdashdot'];

// helper: pick marker/dash per tag index
const getTagMarker = (idx) => TAG_MARKERS[idx % TAG_MARKERS.length];
const getTagDash   = (idx) => TAG_DASHES[idx % TAG_DASHES.length];

/**
 * CompoundPlot component.
 *
 * @component
 * @param {Object} props
 * @param {CompoundPlotRow[]} props.compoundGroup
 * Group of rows corresponding to a single compound ID across tags/adducts.
 * @param {(payload: PlotExportPayload) => void} [props.onExportReady]
 * Callback invoked when plots are ready for export.
 *
 * @returns {JSX.Element}
 * Interactive stacked MS1/MS2 visualization.
 *
 * @state {boolean} useRelative
 * If true, MS2 and fragment intensities are scaled to relative intensity (0–1).
 *
 * @state {Object|null} plotObj
 * Plotly-compatible data and layout object for rendering.
 *
 * @remarks
 * - MS2 spectra are aligned to the closest MS2 scan relative to the MS1 apex.
 * - Color assignment is consistent per tag/adduct combination.
 */


const CompoundPlot = ({ compoundGroup, onExportReady, onPeaksReady, theme }) => {
  
  const [useRelative, setUseRelative] = useState(true);
  const [fragmentsGreyscale, setFragmentsGreyscale] = useState(false);
  const [eicFillEnabled, setEicFillEnabled] = useState(false);
  const { appState } = useAppState();
  const [plotObj, setPlotObj] = useState(null);
  const [structureInfo, setStructureInfo] = useState(null);
  const [mzText, setMzText] = useState('');
  const [publicationMode, setPublicationMode] = useState(false);
  const [axisRanges, setAxisRanges] = useState({}); // e.g. { xaxis:[min,max], yaxis:[min,max], xaxis2:..., ... }
  const [uiRev, setUiRev] = useState('keep');       // Plotly will keep zoom across re-renders while this stays constant
  const plotDivRef = useRef(null); 
  const isAutoScalingRef = useRef(false);
  
  const handleRelayout = (e) => {
    const next = { ...axisRanges };

    ['xaxis','yaxis','xaxis2','yaxis2','xaxis3','yaxis3'].forEach(ax => {
      const r0 = e[`${ax}.range[0]`];
      const r1 = e[`${ax}.range[1]`];
      if (r0 !== undefined && r1 !== undefined) next[ax] = [r0, r1];
      if (e[`${ax}.autorange`] === true) delete next[ax];
    });

    setAxisRanges(next);

    // if any axis triggered autorange, reset all
    if (Object.keys(e).some(k => k.endsWith('.autorange') && e[k] === true)) {
      setAxisRanges({});
      if (plotDivRef.current) autoscaleAllAxes(plotDivRef.current);
    }
  };

const resetZoom = () => {
  setAxisRanges({});
  setUiRev(String(Date.now()));
  if (plotDivRef.current) {
    autoscaleAllAxes(plotDivRef.current);
  }
};
function autoscaleAllAxes(gd) {
  if (!gd || !gd._fullLayout) return;

  // Only include axes that exist on this figure
  const axKeys = Object.keys(gd._fullLayout).filter(k => /^(xaxis|yaxis)\d*$/.test(k));
  if (axKeys.length === 0) return;

  // Avoid recursive calls
  if (isAutoScalingRef.current) return;
  isAutoScalingRef.current = true;

  // Build payload with autorange flags for all axes
  const payload = {};
  axKeys.forEach(k => { payload[`${k}.autorange`] = true; });

  // Perform relayout and also trigger Plotly's internal autoscale recompute
  Plotly.relayout(gd, payload).then(() => {
    Plotly.Plots.resize(gd);
    isAutoScalingRef.current = false;
  }).catch(() => {
    isAutoScalingRef.current = false;
  });
}


const exportFilename = useMemo(() => {
    const first = compoundGroup?.[0];
    const name = (structureInfo?.name || first?.Name || 'compound') + '';
    const mz = first?.mz != null ? Number(first.mz).toFixed(4) : 'mz';
    return `${name.replace(/[^a-z0-9]+/gi, '_')}_mZ_${mz}`;
  }, [structureInfo, compoundGroup]);

  /**
 * Generate Plotly traces for MS1, MS2, and fragment spectra.
 *
 * @effect
 * Recomputed whenever:
 * - Selected compound group changes
 * - Relative/absolute intensity mode changes
 *
 * @workflow
 * 1) Determine MS1 apex from EIC
 * 2) Select closest MS2 scan by retention time
 * 3) Render MS1 EIC, MS2 precursor marker, and fragment peaks
 * 4) Emit export-ready plot payload
 *
 * @sideEffects
 * - Updates Plotly data/layout state
 * - Calls `onExportReady` with export payload
 */
 
  useEffect(() => {
    const fetchData = async () => {
      if (!compoundGroup?.length || !appState?.working_directory) return;
      
      const retTimeShiftTol = await loadExtractionConfig(appState.working_directory);
      let data = [];
      let maxMS1Y = 0;
      let maxFragmentY = 0;
      
      const compTable = await loadComprehensiveTable(appState.working_directory);
      const first = compoundGroup[0];
      const toNumber = (v) => {
        const n = parseFloat(String(v ?? '').replace(/[^\d.+\-eE]/g, ''));
        return Number.isFinite(n) ? n : 0.5;
      };
      const halfWindow = toNumber(retTimeShiftTol);
      const rtHint = parseFloat(first.rt);
      const hasRT = Number.isFinite(rtHint);
      const match = compTable.find(r => r.ID === first.ID);
      if (match) setStructureInfo({ smiles: match.SMILES, name: match.Name });

      //const identifiers = compoundGroup.map(c => `${c.tag}_${c.adduct}`);
      //const uniqueIds = Array.from(new Set(identifiers));
      //const colors = chroma.scale('Set1').colors(uniqueIds.length);
         
      const uniqueTags = Array.from(new Set(compoundGroup.map(c => c.tag)));
      const peaksByKey = {}; // top MS1 peaks per row, offered for manual peak selection

      for (const compound of compoundGroup) {
        const { ID, tag, adduct } = compound;
        const color = getTagColor(tag, uniqueTags);
        const tagIdx = uniqueTags.indexOf(tag);
        const dash = publicationMode ? getTagDash(tagIdx) : 'solid';
        const markerSymbol = publicationMode ? getTagMarker(tagIdx) : 'x';
        const compoundId = ID;

        const ms1Data = await loadCSV(compoundId, 'EIC', tag, adduct, appState.working_directory);
        const ms2Data = await loadCSV(compoundId, 'MS2', tag, adduct, appState.working_directory);

        // let ms1RT = 'N/A';
        if (ms1Data.length) {
          const rts = ms1Data.map((row) => parseFloat(row.rt));
          const intensities = ms1Data.map((row) => parseFloat(row.intensity));
          maxMS1Y = Math.max(maxMS1Y, ...intensities);

          const topPeaks = findTopPeaks(rts, intensities, {
            n: 3,
            minSeparation: 0.15,
            prominenceFrac: 0.05,
            minWidthPoints: 3,
          });
          peaksByKey[`${ID}_${adduct}_${tag}`] = topPeaks.map((p) => ({ rt: p.rt, intensity: p.intensity }));

                        
          topPeaks.forEach((pk, i) => {
            const lg = `peak-${compoundId}-${i + 1}`;
            const rtStr = isFinite(pk.rt) ? pk.rt.toFixed(2) : 'N/A';
            const intStr = isFinite(pk.intensity) ? pk.intensity.toExponential(2) : 'N/A';
            const adductLabel = adduct ? ` | ${adduct}` : '';

          // Full EIC trace inside peak group
          
            data.push({
              x: rts,
              y: intensities,
              mode: 'lines',
              name: `MS1 | ${tag} | RT: ${rtStr}${adductLabel} | ${compoundId} | I: ${intStr}`,
              xaxis: 'x1',
              yaxis: 'y1',
              showlegend: false,
              legendgroup: lg,
              visible: i === 0 ? true : 'legendonly',
              line: { shape: 'spline', width: publicationMode ? PUB.lineWidth : 2, color, dash },
              fill: eicFillEnabled ? 'tozeroy' : 'none',
              fillcolor: eicFillEnabled ? chroma(color).alpha(0.18).css() : 'rgba(0,0,0,0)',
            });

            // Peak marker in EIC
            data.push({
              x: [pk.rt],
              y: [pk.intensity],
              mode: 'markers',
              marker: { size: publicationMode ? PUB.markerSize : 10, symbol: markerSymbol, color },
              name: `MS1 | ${tag} | RT: ${rtStr}${adductLabel} | ${compoundId} | I: ${intStr}`,
              legendgroup: lg,
              xaxis: 'x1',
              yaxis: 'y1',
              showlegend: true,
              visible: i === 0 ? true : 'legendonly',
            });

            if (ms2Data.length) {
              const candidates = ms2Data
                .map((m) => ({ ...m, rt: parseFloat(m.ms2_rt) }))
                .filter((m) => isFinite(m.rt) && Math.abs(m.rt - pk.rt) <= retTimeShiftTol);


            if (candidates.length) {
              const closest = candidates.reduce((a, b) =>
                Math.abs(a.rt - pk.rt) < Math.abs(b.rt - pk.rt) ? a : b
              );


              data.push({
                x: [closest.rt, closest.rt],
                y: useRelative ? [0, 1050] : [0, maxMS1Y * 1.1],
                mode: 'lines',
                name: `MS2 Peak | ${tag} | RT: ${closest.rt.toFixed(2)}${adductLabel} | ${compoundId}`,
                line: { dash: 'dash', color, width: publicationMode ? 2.5 : 2 },
                xaxis: 'x2',
                yaxis: 'y2',
                showlegend: true,
                legendgroup: lg,
                visible: i === 0 ? true : 'legendonly',
              });


              const peaks = parsePeakList(closest.peak_list || '');
              if (peaks.length) {
                const maxY = Math.max(...peaks.map((p) => p.y));
                maxFragmentY = useRelative ? 1050 : Math.max(maxFragmentY, maxY);
                peaks.forEach((p) => {
                  const yVal = useRelative ? (p.y / maxY) * 1050 : p.y;
                  data.push({
                    x: [p.x, p.x],
                    y: [0, yVal],
                    mode: 'lines',
                    type: 'scatter',
                    line: { width: 2, color: fragmentsGreyscale ? '#6B7280' : color },
                    name: `Fragment | ${tag} | ${compoundId}`,
                    showlegend: false,
                    xaxis: 'x3',
                    yaxis: 'y3',
                    legendgroup: lg,
                    visible: i === 0 ? true : 'legendonly',
                  });
                });
              }
            }
          }
        });
      }
    }

      // Build layout AFTER data so ranges can use computed max/min (FIX)
       const hasName =
          !!first?.Name &&
          String(first.Name).trim().toLowerCase() !== 'null';
        const layout = {
        height: 1200,
        width: 1000,
        margin: { l: 80, r: 60, t: 40, b: 50 },
        grid: { rows: 3, columns: 1, pattern: 'independent', roworder: 'top to bottom' },
        title: {
          text: hasName
            ? `Mass Spectra Overview — Name: ${String(first.Name).trim()} | m/z: ${parseFloat(first.mz).toFixed(4)}`
            : `Mass Spectra Overview — m/z: ${parseFloat(first.mz).toFixed(4)}`,
           xanchor: 'left',
          x: 0
        }, 
        font: { family: PUB.fontFamily, size: publicationMode ? PUB.tickSize : 12 },    
        showlegend: true,
        legend: {
          groupclick: 'togglegroup',
          orientation: 'v',
        },
        uirevision: uiRev,
      

        // EIC
        xaxis: { title:{ text: 'RT (min)',font: { size: publicationMode ? PUB.axisLabelSize : 12 }},tickfont: { size: publicationMode ? PUB.tickSize : 12 }, showline: true, linewidth: 1, linecolor: '#000', mirror: 'allticks', range: hasRT ? [rtHint - halfWindow, rtHint + halfWindow] : [0, 30], ticks: 'outside', ticklen: 6, tickwidth: 1,
                 gridcolor: PUB.grid, zeroline: false, anchor: 'y1', ...(axisRanges.xaxis ? { autorange: false, range: axisRanges.xaxis } : {}) },
        yaxis: { title: { text: 'MS1 Intensity' }, tickfont: { size: publicationMode ? PUB.tickSize : 12 },
                tickformat: '.2e',
                showline: true, linewidth: 1, linecolor: '#000', mirror: 'allticks',
                ticks: 'outside', ticklen: 6, tickwidth: 1,
                gridcolor: PUB.grid, zeroline: false, anchor: 'x1', ...(axisRanges.yaxis ? { autorange: false, range: axisRanges.yaxis } : {}) },

         // MS2 RT lines        
        xaxis2: { title:{ text: 'RT (min)',font: { size: publicationMode ? PUB.axisLabelSize : 12 }},tickfont: { size: publicationMode ? PUB.tickSize : 12 }, showline: true, linewidth: 1, linecolor: '#000', mirror: 'allticks', range: [0, 30], ticks: 'outside', ticklen: 6, tickwidth: 1,
                 gridcolor: PUB.grid, zeroline: false, matches: 'x', anchor: 'y2', ...(axisRanges.xaxis ? { /* no axisRanges.xaxis2 when matched */ } : {}) },
        yaxis2: {
          title: { text: 'MS2 Intensity', font: { size: publicationMode ? PUB.axisLabelSize : 12 }},
          range: useRelative ? [0, 1050] : [0, maxMS1Y * 1.1],
          showline: true, linewidth: 1, linecolor: '#000', mirror: 'allticks',
          ticks: 'outside', ticklen: 6, tickwidth: 1,
          gridcolor: PUB.grid, zeroline: false,
          tickformat: useRelative ? '' : '.2e',
          anchor: 'x2', ...(axisRanges.yaxis2 ? { autorange: false, range: axisRanges.yaxis2 } : {})
        },

         // Fragment sticks (FIX: dynamic m/z range)
        xaxis3: { title:{ text: 'm/z',font: { size: publicationMode ? PUB.axisLabelSize : 12 }},tickfont: { size: publicationMode ? PUB.tickSize : 12 }, showline: true, linewidth: 1, linecolor: '#000', mirror: 'allticks', autorange: true, ticks: 'outside', ticklen: 6, tickwidth: 1,
                 gridcolor: PUB.grid, zeroline: false, anchor: 'y3', ...(axisRanges.xaxis3 ? { autorange: false, range: axisRanges.xaxis3 } : {}) },
        yaxis3: {
          title: { text: 'Fragment Intensity', tickfont: { size: publicationMode ? PUB.tickSize : 12 } },
          range: useRelative ? [0, 1050] : [0, maxFragmentY * 1.1],
          showline: true, linewidth: 1, linecolor: '#000', mirror: 'allticks',
          ticks: 'outside', ticklen: 6, tickwidth: 1,
          gridcolor: PUB.grid, zeroline: false,
          tickformat: useRelative ? '' : '.2e',
          anchor: 'x3', ...(axisRanges.yaxis3 ? { autorange: false, range: axisRanges.yaxis3 } : {})
        }
      };

      setPlotObj({ data, layout });
      if (onPeaksReady) onPeaksReady(peaksByKey);
      setMzText(`Name: ${first.Name} | m/z: ${parseFloat(first.mz).toFixed(4)}`);

      if (onExportReady && match?.SMILES) {
        const smilesUrl = `https://cactus.nci.nih.gov/chemical/structure/${encodeURIComponent(match.SMILES)}/image?height=180&width=180&title=${encodeURIComponent(match.Name || 'Unknown')}`;
        onExportReady({ plots: [{ id: 'stackedPlot', data, layout }], smilesUrl });
      }
    };

    fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [compoundGroup, appState, useRelative, fragmentsGreyscale,eicFillEnabled, publicationMode, onExportReady]);


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
        <label style={{ display: 'flex', gap: '0.25rem', fontSize: '0.875rem', color: '#374151', alignItems: 'center' }}>
        <input type="checkbox" checked={fragmentsGreyscale} onChange={(e) => setFragmentsGreyscale(e.target.checked)} />
              Greyscale MS2 fragments
        </label>
        <label style={{ display: 'flex', gap: '0.25rem', fontSize: '0.875rem', color: '#374151', alignItems: 'center' }}>
        <input type="checkbox" checked={eicFillEnabled} onChange={(e) => setEicFillEnabled(e.target.checked)} />
         Colour fill EIC peak
        </label>

        <label style={{ display: 'flex', gap: '0.25rem', fontSize: '0.875rem', color: '#374151', alignItems: 'center' }}>
        <input type="checkbox" checked={publicationMode} onChange={(e) => setPublicationMode(e.target.checked)}/> 
            Publication mode
        </label>
      </div>

      {plotObj ? (
        <Plot
          data={plotObj.data}
          layout={plotObj.layout}
          style={{ width: '100%', height: '100%' }}
          onInitialized={(_, gd) => { plotDivRef.current = gd; }}
          onRelayout={handleRelayout}
          config={{
              responsive: true,
              displaylogo: false,
              modeBarButtonsToRemove: ['toImage'],              
              modeBarButtonsToAdd: [

              {
                name: 'Reset zoom',
                title: 'Reset zoom on all plots',
                icon: Plotly.Icons.autoscale,
                click: resetZoom,
              },
              {
                name: 'Autoscale all axes',
                icon: Plotly.Icons.autoscale,
                click: (gd) => {
                    setAxisRanges({});
                    autoscaleAllAxes(gd);
                  },
             },
                             
            {
                name: 'Download SVG',
                icon: Plotly.Icons.camera,
                click: (gd) => {Plotly.downloadImage(gd, {format: 'svg',filename: exportFilename });
                },
            },
            {
              name: 'Download PNG (2x)',
              icon: Plotly.Icons.camera,
              click: (gd) => {
              const w = gd._fullLayout?.width || 1000;
              const h = gd._fullLayout?.height || 800;
              Plotly.downloadImage(gd, {
              format: 'png',
              filename: exportFilename,
              width: w,
              height: h,
              scale: 2,
            });
           },
          },
         ],
         doubleClick: 'reset',
        }}
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
          background: theme?.panelLite ?? '#f7f7f7',
          color: theme?.text ?? '#000',
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
