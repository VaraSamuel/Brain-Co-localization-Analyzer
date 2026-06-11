from __future__ import annotations

import os
import shutil
import tempfile

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from analysis import analyze_images

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

app = FastAPI(title="Brain Co-localization Analyzer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "message": "Brain Co-localization Analyzer backend is running",
        "method": "green-cell-first automatic analysis",
    }


def save_upload(upload: UploadFile, folder: str, filename: str) -> str:
    path = os.path.join(folder, filename)
    with open(path, "wb") as f:
        shutil.copyfileobj(upload.file, f)
    return path


@app.post("/analyze")
def analyze(
    green: UploadFile = File(...),
    red: UploadFile = File(...),
    blue: UploadFile = File(...),
):
    """Analyze uploaded channels with no manual parameter tuning.

    Green is segmented into cells first. Red and blue fluorescence are then
    measured inside each green cell mask to classify red-positive, blue-positive,
    and double-positive cells.
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        green_path = save_upload(green, tmpdir, "green.png")
        red_path = save_upload(red, tmpdir, "red.png")
        blue_path = save_upload(blue, tmpdir, "blue.png")

        result = analyze_images(green_path, red_path, blue_path, OUTPUT_DIR)
        result["overlay_url"] = f"/outputs/{result['overlay_file']}"
        result["csv_url"] = f"/outputs/{result['csv_file']}"
        return result


@app.get("/outputs/{filename}")
def get_output(filename: str):
    path = os.path.join(OUTPUT_DIR, filename)
    return FileResponse(path)


FRONTEND_DIST = os.path.join(BASE_DIR, "..", "frontend", "dist")
if os.path.isdir(FRONTEND_DIST):
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
