import { useState, useEffect, useRef } from 'react';
import { saveState, loadState, generateTable } from '../api/api';
import { useAppState } from '../context/AppStateContext';
import { useNavigate } from 'react-router-dom';
import RibbonHeader from "../components/RibbonHeader";


// --- dark mode support (inline, no CSS files) ---
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
    // addEventListener is modern; addListener is older WebKit
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
        tableHeader: '#111827',
        inputBg: '#0b1220',
        inputText: '#e5e7eb',
        btnBg: '#1f2937',
        btnText: '#e5e7eb',
        dangerText: '#ff7b7b'
      }
    : {
        bg: '#e0f4f7',
        panel: '#ffffff',
        panelLite: '#f0faff',
        text: '#111827',
        muted: '#374151',
        border: '#D1D5DB',
        tableHeader: '#f2f2f2',
        inputBg: '#ffffff',
        inputText: '#111827',
        btnBg: '#a7cce5',
        btnText: '#111827',
        dangerText: 'red'
      };

 /** Inline Adduct multi-select dropdown
 * - stays open while toggling checkboxes
 * - closes on Done
 * - closes on outside click
 */
function AdductPicker({
  theme,
  value,
  onChange,
  positiveOptions = ["[M+H]+","[M+Na]+","[M+K]+","[M+NH4]+","[M+2H]2+"],
  negativeOptions = ["[M-H]-","[M+Cl]-","[M+FA-H]-","[M-2H]2-"]
}) {
  const [open, setOpen] = useState(false);
  const panelRef = useRef(null);
  const btnRef = useRef(null);

  useEffect(() => {
    function onDocClick(e) {
      if (
        panelRef.current &&
        !panelRef.current.contains(e.target) &&
        btnRef.current &&
        !btnRef.current.contains(e.target)
      ) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, []);

  const total =
    (value?.positive?.length || 0) + (value?.negative?.length || 0);
  const label = total ? `Adducts (${total})` : 'Select Adduct/Adducts';

  const toggle = (pol, adduct) => {
    const cur = new Set(value?.[pol] || []);
    if (cur.has(adduct)) cur.delete(adduct);
    else cur.add(adduct);
    onChange?.({ ...value, [pol]: Array.from(cur) });
  };

  return (
    <div style={{ position: 'relative', display: 'inline-block' }}>
      <button
        ref={btnRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        style={{
          padding: '8px 12px',
          borderRadius: 6,
          border: `1px solid ${theme.border}`,
          background: theme.btnBg,
          color: theme.btnText
        }}
      >
        {label}
      </button>

      {open && (
        <div
          ref={panelRef}
          style={{
            position: 'absolute',
            top: '110%',
            zIndex: 20,
            width: "min(420px, 85vw)",
            boxSizing: "border-box",
            border: `1px solid ${theme.border}`,
            borderRadius: 8,
            padding: 12,
            background: theme.panel,
            color: theme.text,
            boxShadow: '0 8px 24px rgba(0,0,0,0.12)'
          }}
        >
          <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
            <section style={{ flex: 1, minWidth: 200 }}>
              <h4 style={{ margin: '4px 0 8px' }}>Positive</h4>
              <div style={{ maxHeight: 240, overflow: 'auto', paddingRight: 4 }}>
                {positiveOptions.map((a) => (
                  <label key={a} style={{ display: 'flex', gap: 8, marginBottom: 6, alignItems: 'center' }}>
                    <input
                      type="checkbox"
                      checked={value?.positive?.includes(a) || false}
                      onChange={() => toggle('positive', a)}
                    />
                    <span>{a}</span>
                  </label>
                ))}
              </div>
            </section>
            <section style={{ flex: 1, minWidth: 200 }}>
              <h4 style={{ margin: '4px 0 8px' }}>Negative</h4>
              <div style={{ maxHeight: 240, overflow: 'auto', paddingRight: 4 }}>
                {negativeOptions.map((a) => (
                  <label key={a} style={{ display: 'flex', gap: 8, marginBottom: 6, alignItems: 'center' }}>
                    <input
                      type="checkbox"
                      checked={value?.negative?.includes(a) || false}
                      onChange={() => toggle('negative', a)}
                    />
                    <span>{a}</span>
                  </label>
                ))}
              </div>
            </section>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 12 }}>
            <button
              type="button"
              onClick={() => onChange?.({ positive: [], negative: [] })}
              style={{ border: `1px solid ${theme.border}`, borderRadius: 6, padding: '6px 10px', background: 'transparent', color: theme.text }}
            >
              Clear
            </button>
            <button
              type="button"
              onClick={() => setOpen(false)}
              style={{ border: `1px solid ${theme.border}`, borderRadius: 6, padding: '6px 10px', background: theme.btnBg, color: theme.btnText }}
            >
              Done
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

const LandingPage = () => {
  const { appState, updateAppState } = useAppState();
  const [draggedRowIndex, setDraggedRowIndex] = useState(null);
  const isDark = usePrefersDark();
  const theme = makeTheme(isDark);
  const [globalAdducts, setGlobalAdducts] = useState({ positive: [], negative: [] });
  const [isGenerating, setIsGenerating] = useState(false);
  const navigate = useNavigate();
  const [workingDirectory, setWorkingDirectory] = useState("/app/uploads/");
  const [compoundCSV, setCompoundCSV] = useState(null);
  const [mzmlFiles, setMzmlFiles] = useState([]);
  const [tags, setTags] = useState({});

  useEffect(() => {
  if (appState.working_directory && mzmlFiles.length === 0) {
    setWorkingDirectory(appState.working_directory || '');

    const files = appState.mzml_files.map(f => ({ name: f.file.split('/').pop() }));
    setMzmlFiles(files);

    const loadedTags = {};
    appState.mzml_files.forEach(f => {
      const fname = f.file.split('/').pop();
      loadedTags[fname] = f.tag;
    });

    setTags(loadedTags);
  }
}, [appState, mzmlFiles.length]);


const handleSaveState = async () => {
  // 1) Build mzML entries WITHOUT per-file adducts
  const mzmlData = mzmlFiles.map(file => ({
    file: file.name,
    tag: tags[file.name] || ''
  }));

  // 2) Build payload INCLUDING the two flat adduct keys
  const payload = {
    working_directory: workingDirectory || "/app/uploads",
    compound_csv: compoundCSV?.name || '',
    mzml_files: mzmlData,
    // 👇 send global selections (from your AdductPicker state)
    positive_adducts: globalAdducts?.positive || [],
    negative_adducts: globalAdducts?.negative || []
  };

  // 3) Update context (optional), then save
  updateAppState({
    ...payload,
    adducts: { positive: payload.positive_adducts, negative: payload.negative_adducts }
  });


  // Then save to backend
  try {
    await saveState(payload);             // <-- sends exactly what backend expects
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
      data.mzml_files.forEach(f => {
        const fname = f.file.split('/').pop();
        loadedTags[fname] = f.tag;
      });

      setTags(loadedTags);
      
      alert('State loaded!');
    } catch (err) {
      console.error("Load failed:", err);
      alert('Failed to load state.');
    }
  };

  const handleGenerateTable = async () => {
    const payload = { workingDirectory };

    console.log("[Generate] clicked with payload:", payload);
    setIsGenerating(true);
    try {
      const res = await generateTable({workingDirectory});
      console.log("Generate response:", res?.data);
      alert(res?.data?.message || "Table generated successfully!");
    } catch (err) {
      const data = err?.response?.data;
      console.error("[Generate] failed:", err?.message, data);
      alert("Generate failed:\n" +
      (data?.error || err?.message || "Unknown error"));
    }finally {
    setIsGenerating(false);
    }
  };
 
  const handleDeleteRow = (fileName) => {
  setMzmlFiles(prev => prev.filter(file => file.name !== fileName));
  setTags(prev => {
    const updated = { ...prev };
    delete updated[fileName];
    return updated;
  });
  
};
 
  // Inject keyframes for underline animation once
useEffect(() => {
  const animation = `
    @keyframes header-underline {
      0% { background-position: 0%; }
      100% { background-position: 200%; }
    }
  `;
  const style = document.createElement('style');
  style.textContent = animation;
  document.head.appendChild(style);
  return () => document.head.removeChild(style);
}, []);

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
        Mass Spectrometry Data Pre-screening

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
        An application intended to give the user a first look into raw
        mass-spectrometry data. This currently means that, given the input of
        data files and a list of masses of known or unknown compounds, the
        application is going to produce MS1 and MS2 chromatograms of the
        substances in the list, as well as the MS2 spectra.
      </p>
    </div>

    {/* DATA CONFIG BLOCK */}
    <div
      className="data-config"
      style={{
        padding: "20px",
        backgroundColor: theme.panel,
        color: theme.text,
        margin: "20px auto",
        borderRadius: "12px",
        boxShadow: "0 6px 12px rgba(0, 0, 0, 0.15)",
        border: `2px solid ${theme.border}`,
        maxWidth: "90%",
        width: "min(900px, 92vw)",
        boxSizing: "border-box",
      }}
    >
      <h2>Data Configuration</h2>

      <div style={{ marginBottom: "10px" }}>
        <details
          style={{
            background: theme.panelLite,
            color: theme.text,
            padding: "10px",
            borderRadius: "8px",
            border: "1px solid #cceeff",
          }}
        >
          <summary style={{ cursor: "pointer", fontWeight: "bold" }}>
            ℹ️ Instructions
          </summary>
          <ol style={{ paddingLeft: "20px", marginTop: "10px" }}>
            <li>
              The <strong>Working Directory</strong> is set to <code>/app/uploads</code> by default. This directory is mapped to a folder on your local machine through Docker, so all uploaded files and generated outputs are saved and persist outside the container.  
            </li>
            <li>Upload the <strong>Compound CSV</strong>…</li>
            <li>Upload one or more <strong>mzML Files</strong>.</li>
            <li>Edit Tags and select the appropriate Adduct.</li>
            <li>Click Save State, then Generate Table.</li>
            <li>Load State retrieves saved configuration.</li>
            <li>Proceed to Extraction & Prescreening.</li>
          </ol>
        </details>
      </div>

      <div style={{ display: "grid", gap: 16 }}>
        <div>
          <label style={{ display: "block", marginBottom: 6 }}>
            Working Directory:
          </label>
          <input
            type="text"
            value={workingDirectory}
            disabled
            style={{
              width: "100%",
              boxSizing: "border-box",
              padding: "8px 10px",
              backgroundColor: theme.inputDisabledBg || theme.panelLite,  
              color: theme.inputDisabledText || theme.text,  
              opacity: 0.7,               
              cursor: "not-allowed",       
              border: `1px solid ${theme.border}`,
              borderRadius: 6,
            }}
          />
        </div>

      <div>
        <label style={{ display: "block", marginBottom: 6 }}>
          Compound CSV:
        </label>
        <input
          type="file"
          accept=".csv"
          onChange={(e) => setCompoundCSV(e.target.files[0])}
          style={{
            width: "100%",
            boxSizing: "border-box",
            padding: "8px",
            backgroundColor: theme.panelLite,
            color: theme.text,
            border: `1px solid ${theme.border}`,
            borderRadius: 6,
          }}
        />
      </div>

      <div>
        <label style={{ display: "block", marginBottom: 6 }}>
          mzML Files:
        </label>
        <input
          type="file"
          accept=".mzML"
          multiple
          onChange={(e) => setMzmlFiles([...e.target.files])}
          style={{
            width: "100%",
            boxSizing: "border-box",
            padding: "8px",
            backgroundColor: theme.panelLite,
            color: theme.text,
            border: `1px solid ${theme.border}`,
            borderRadius: 6,
          }}
        />
      </div>

      <div>
        <label style={{ display: "block", marginBottom: 6 }}>
          Adducts:
        </label>
        <AdductPicker theme={theme} value={globalAdducts} onChange={setGlobalAdducts} />
      </div>
    </div>

    {/* TABLE BLOCK */}
    <table style={{ width: "90%", margin: "20px auto", tableLayout: "fixed", borderCollapse: "separate", borderSpacing: "0 10px", backgroundColor: theme.panelLite}}>
      <thead>
        <tr style={{ backgroundColor: theme.bg, color: theme.text }}>
          <th style={{ width: "50%", border: `1px solid ${theme.border}`, padding: "12px 14px" }}>
            File Name
          </th>
          <th style={{ width: "30%", border: `1px solid ${theme.border}`, padding: "12px 14px" }}>
            Tag
          </th>
          <th style={{  width: "20%", border: `1px solid ${theme.border}`, padding: "12px 14px" }}>
            Actions
          </th>
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
            style={{
              cursor: "move"
            }}
          >
            <td style={{ padding: "12px 14px" }}>
              <div
                title={file.name}
                style={{
                  width: "100%",
                  boxSizing: "border-box",
                  padding: "12px 14px",
                  backgroundColor: theme.inputBg,
                  color: theme.inputText,
                  border: `1px solid ${theme.border}`,
                  borderRadius: 6,
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                }}
              >
                {file.name}
              </div>
            </td>

            <td style={{ padding: "12px 14px"}}>
              <input
                type="text"
                value={tags[file.name] || ""}
                onChange={(e) =>
                  setTags((prev) => ({ ...prev, [file.name]: e.target.value }))
                }
                style={{
                  width: "100%",
                  boxSizing: "border-box",
                  padding: "12px 14px",
                  backgroundColor: theme.inputBg,
                  color: theme.inputText,
                  border: `1px solid ${theme.border}`,
                  borderRadius: 6,
                }}
              />
            </td>

            <td style={{padding: "12px 14px" }}>
              <button
                onClick={() => handleDeleteRow(file.name)}
                style={{
                  color: theme.dangerText,
                  background: "transparent",
                  border: `1px solid ${theme.border}`,
                  borderRadius: 6,
                  padding: "6px 10px",
                }}
              >
                Delete
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>

    {/* ACTION BUTTONS */}
    <div
      style={{
        display: "flex",
        justifyContent: "flex-start",
        maxWidth: "90%",
        margin: "20px auto",
      }}
    >
      <button
        onClick={handleSaveState}
        style={{
          padding: "10px 15px",
          marginRight: "5px",
          borderRadius: "5px",
          background: theme.btnBg,
          color: theme.btnText,
          border: `1px solid ${theme.border}`,
        }}
      >
        Save State
      </button>

      <button
        onClick={handleLoadState}
        style={{
          padding: "10px 15px",
          marginRight: "5px",
          borderRadius: "5px",
          background: theme.btnBg,
          color: theme.btnText,
          border: `1px solid ${theme.border}`,
        }}
      >
        Load State
      </button>

      <button
        onClick={handleGenerateTable}
        disabled={isGenerating}
        style={{
          padding: "10px 15px",
          borderRadius: "5px",
          background: theme.btnBg,
          color: theme.btnText,
          border: `1px solid ${theme.border}`,
          opacity: isGenerating ? 0.7 : 1,
          cursor: isGenerating ? "not-allowed" : "pointer",
        }}
      >
        {isGenerating ? "Generating…" : "Generate Table"}
      </button>
    </div>

    {/* NEXT PAGE BUTTON */}
    <div
      style={{
        textAlign: "right",
        maxWidth: "90%",
        margin: "auto",
        marginTop: "20px",
      }}
    >
      <button
        onClick={() => navigate("/extraction")}
        style={{
          padding: "10px 15px",
          borderRadius: "5px",
          background: theme.btnBg,
          color: theme.btnText,
          border: `1px solid ${theme.border}`,
        }}
      >
        Go to Extraction & Prescreening
      </button>
    </div>

  </div>
    {/* END WRAPPER */}
  </div>
);
};

export default LandingPage;
