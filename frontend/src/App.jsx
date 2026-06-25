import React, { useState } from 'react';

const API_BASE = import.meta.env.VITE_API_URL ?? '';

const VIEWS = [
  { key: 'all', label: 'All Cells' },
  { key: 'double', label: 'Red + Blue Overlap' },
  { key: 'red_positive', label: 'Green + Red' },
  { key: 'blue_positive', label: 'Green + Blue' },
];

const VIEW_DESCRIPTIONS = {
  all: 'All segmented green cells, coloured by classification: green = green only, red = red marker positive, blue = blue marker positive, yellow = both markers present.',
  double: 'Only cells positive for both red and blue markers (double-positive). All other cells shown as faint outlines for spatial context.',
  red_positive: 'Cells positive for the red marker (including double-positives). All other cells shown as faint outlines.',
  blue_positive: 'Cells positive for the blue marker (including double-positives). All other cells shown as faint outlines.',
};

function FileInput({ label, helper, file, setFile }) {
  return (
    <label className="file-card">
      <span>{label}</span>
      <small>{helper}</small>
      <input type="file" accept="image/*" onChange={(e) => setFile(e.target.files[0])} />
      <em>{file ? file.name : 'No file selected'}</em>
    </label>
  );
}

function StatCard({ label, value, note }) {
  return (
    <div className="stat">
      <span>{label}</span>
      <strong>{value}</strong>
      {note && <small>{note}</small>}
    </div>
  );
}

export default function App() {
  const [green, setGreen] = useState(null);
  const [red, setRed] = useState(null);
  const [blue, setBlue] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [activeView, setActiveView] = useState('all');

  async function runAnalysis() {
    if (!green || !red || !blue) {
      setError('Please upload green, red, and blue images.');
      return;
    }

    setLoading(true);
    setError('');
    setResult(null);
    setActiveView('all');

    const formData = new FormData();
    formData.append('green', green);
    formData.append('red', red);
    formData.append('blue', blue);

    try {
      const response = await fetch(`${API_BASE}/analyze`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error('Analysis failed. Check the backend terminal.');
      }

      const data = await response.json();
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const currentOverlayUrl = result?.overlay_urls?.[activeView] ?? result?.overlay_url;

  return (
    <main className="page">
      <section className="hero">
        <p className="eyebrow">Automatic fluorescence co-localization</p>
        <h1>Brain Co-localization Analyzer</h1>
        <p>
          Upload green, red, and blue channels. The backend automatically segments green cells first,
          then measures red and blue signal inside each green cell to count marker-positive and double-positive cells.
        </p>
      </section>

      <section className="panel">
        <div className="grid">
          <FileInput
            label="Green channel"
            helper="Master cell/body channel"
            file={green}
            setFile={setGreen}
          />
          <FileInput
            label="Red channel"
            helper="TRPA1 or red marker"
            file={red}
            setFile={setRed}
          />
          <FileInput
            label="Blue channel"
            helper="TRPV1 or blue marker"
            file={blue}
            setFile={setBlue}
          />
        </div>

        <div className="auto-box">
          <strong>Automatic mode enabled</strong>
          <p>No manual min area, max area, or overlap distance is needed. Thresholds and cell-size limits are estimated from the images.</p>
        </div>

        <button onClick={runAnalysis} disabled={loading}>
          {loading ? 'Analyzing...' : 'Analyze Brain'}
        </button>

        {error && <p className="error">{error}</p>}
      </section>

      {result && (
        <section className="results">
          <h2>Cell Counts</h2>
          <div className="cards five">
            <StatCard label="Total Green Cells" value={result.total_green} note="all segmented cells" />
            <StatCard label="Green Only" value={result.green_only} note={`${result.green_only_percent}%`} />
            <StatCard label="Red Positive" value={result.total_red} note={`${result.red_percent}% of green`} />
            <StatCard label="Blue Positive" value={result.total_blue} note={`${result.blue_percent}% of green`} />
            <StatCard label="Overlap" value={result.total_overlap} note={`${result.overlap_percent}% double+`} />
          </div>

          <div className="viewer">
            <h2>Annotated Overlay</h2>

            <div className="view-buttons">
              {VIEWS.map(({ key, label }) => (
                <button
                  key={key}
                  className={`view-btn${activeView === key ? ' active' : ''}`}
                  onClick={() => setActiveView(key)}
                >
                  {label}
                </button>
              ))}
            </div>

            <p className="view-desc">{VIEW_DESCRIPTIONS[activeView]}</p>

            <img src={`${API_BASE}${currentOverlayUrl}`} alt="Annotated co-localization overlay" />

            <div className="links">
              <a href={`${API_BASE}${currentOverlayUrl}`} target="_blank" rel="noreferrer">Open overlay</a>
              <a href={`${API_BASE}${result.csv_url}`} target="_blank" rel="noreferrer">Download CSV</a>
            </div>
          </div>

          <details className="settings">
            <summary>Automatic values used</summary>
            <pre>{JSON.stringify(result.auto_settings, null, 2)}</pre>
          </details>

          <h2>Double-positive coordinates</h2>
          <table>
            <thead>
              <tr>
                <th>Cell ID</th>
                <th>X</th>
                <th>Y</th>
                <th>Area</th>
                <th>Red fraction</th>
                <th>Blue fraction</th>
              </tr>
            </thead>
            <tbody>
              {result.overlap_cells.length === 0 && (
                <tr><td colSpan="6">No double-positive cells detected.</td></tr>
              )}
              {result.overlap_cells.map((cell) => (
                <tr key={cell.cell_id}>
                  <td>{cell.cell_id}</td>
                  <td>{cell.x.toFixed(1)}</td>
                  <td>{cell.y.toFixed(1)}</td>
                  <td>{cell.area}</td>
                  <td>{cell.red_positive_fraction}</td>
                  <td>{cell.blue_positive_fraction}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </main>
  );
}
