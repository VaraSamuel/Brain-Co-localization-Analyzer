# Brain Co-localization Analyzer

A local full-stack app for fluorescence microscopy co-localization analysis.

## What changed in this version

This version uses the green channel as the master cell/body channel.

Pipeline:

1. Upload green, red, and blue images.
2. Segment green cells automatically.
3. Measure red and blue signal inside every green cell mask.
4. Classify every green cell as:
   - green only
   - red positive
   - blue positive
   - double positive / overlap
5. Export an annotated overlay and CSV.

No external API is required. The analysis runs locally with OpenCV, NumPy, scikit-image, and FastAPI.

## Backend setup

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

If port 8000 is busy:

```bash
lsof -i :8000
kill -9 <PID>
```

or run another port and update `API_BASE` in `frontend/src/App.jsx`.

## Frontend setup

Open a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Then open the Vite URL shown in the terminal, usually:

```text
http://localhost:5173
```

## Output counts

- Total Green Cells: all segmented cells from the green image.
- Green Only: green cells without red or blue marker signal.
- Red Positive: green cells with red signal.
- Blue Positive: green cells with blue signal.
- Overlap: green cells with both red and blue signal.

## Overlay colors

- Green circle: green only
- Red circle: red-positive
- Blue circle: blue-positive
- Yellow circle: double-positive overlap
