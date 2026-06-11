import React, { useState } from 'react';

const API_BASE = 'http://localhost:8000';

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

  async function runAnalysis() {
    if (!green || !red || !blue) {
      setError('Please upload green, red, and blue images.');
      return;
    }

    setLoading(true);
    setError('');
    setResult(null);

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

          <div className="explanation">
            <h2>What the diagram is showing</h2>
            <p>
              The overlay uses the green channel as the background. Green circles are cells with no red or blue marker,
              red circles are red-positive cells, blue circles are blue-positive cells, and yellow circles are cells where
              red and blue are both detected inside the same green-cell mask.
            </p>
          </div>

          <div className="viewer">
            <h2>Annotated Overlay</h2>
            <img src={`${API_BASE}${result.overlay_url}`} alt="Annotated co-localization overlay" />
            <div className="links">
              <a href={`${API_BASE}${result.overlay_url}`} target="_blank" rel="noreferrer">Open overlay</a>
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
