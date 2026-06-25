from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Dict, List, Tuple

import cv2
import numpy as np
import pandas as pd
from scipy import ndimage as ndi
from skimage import exposure, filters, measure, morphology, segmentation
from skimage.feature import peak_local_max


@dataclass
class AutoConfig:
    """Automatically estimated analysis settings.

    Green is treated as the master cell/body channel. Red and blue are measured
    inside each green cell mask, which gives biologically meaningful counts:
    total green cells, red-positive cells, blue-positive cells, and double-positive cells.
    """

    green_min_area_floor: int = 60
    green_max_area_ceiling: int = 3000
    min_positive_fraction: float = 0.20
    min_positive_signal_ratio: float = 1.50


def read_image(path: str) -> np.ndarray:
    image = cv2.imread(path, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Could not read image: {path}")
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


def resize_to_reference(image: np.ndarray, reference: np.ndarray) -> np.ndarray:
    if image.shape[:2] == reference.shape[:2]:
        return image
    return cv2.resize(image, (reference.shape[1], reference.shape[0]), interpolation=cv2.INTER_LINEAR)


def dominant_channel(image: np.ndarray, channel_name: str) -> np.ndarray:
    channel_map = {"red": 0, "green": 1, "blue": 2}
    return image[:, :, channel_map[channel_name]].astype(np.float32)


def normalize_u8(channel: np.ndarray) -> np.ndarray:
    channel = channel.astype(np.float32)
    lo, hi = np.percentile(channel, [1, 99.7])
    if hi <= lo:
        lo = float(channel.min())
        hi = float(channel.max()) if channel.max() > channel.min() else lo + 1.0
    scaled = np.clip((channel - lo) / (hi - lo), 0, 1)
    return (scaled * 255).astype(np.uint8)


def _estimate_area_limits(candidate_labels: np.ndarray, config: AutoConfig) -> Tuple[int, int, float]:
    areas = np.array([r.area for r in measure.regionprops(candidate_labels)], dtype=float)
    areas = areas[(areas >= config.green_min_area_floor) & (areas <= config.green_max_area_ceiling)]
    if areas.size == 0:
        return 50, 2500, 20.0

    median_area = float(np.median(areas))
    min_area = int(max(config.green_min_area_floor, median_area * 0.30))
    max_area = int(min(config.green_max_area_ceiling, median_area * 5.0))
    diameter = float(np.sqrt(4.0 * median_area / np.pi))
    return min_area, max_area, diameter


def segment_green_cells(green_img: np.ndarray, config: AutoConfig) -> Tuple[np.ndarray, List[Dict], Dict]:
    """Segment cell bodies from the green channel using automatic thresholds.

    This is intentionally local and API-free. It uses contrast normalization,
    background subtraction, Otsu thresholding, morphology, and watershed splitting.
    """

    green_raw = dominant_channel(green_img, "green")
    green_u8 = normalize_u8(green_raw)

    # Larger sigma = gentler background removal, preserves dimmer neurons.
    background = cv2.GaussianBlur(green_u8, (0, 0), 30)
    enhanced = cv2.subtract(green_u8, background)
    enhanced = exposure.rescale_intensity(enhanced, out_range=(0, 255)).astype(np.uint8)
    enhanced = cv2.GaussianBlur(enhanced, (3, 3), 0)

    try:
        otsu = float(filters.threshold_otsu(enhanced))
    except ValueError:
        otsu = float(np.percentile(enhanced, 90))

    # Aggressive threshold to capture dimmer neurons.
    binary = enhanced > max(8, otsu * 0.65)
    binary = morphology.remove_small_objects(binary, min_size=config.green_min_area_floor)
    # Opening removes single-pixel noise; NO closing so adjacent neurons stay separated.
    binary = morphology.binary_opening(binary, morphology.disk(1))
    binary = ndi.binary_fill_holes(binary)

    rough_labels = measure.label(binary)
    min_area, max_area, avg_diameter = _estimate_area_limits(rough_labels, config)

    distance = ndi.distance_transform_edt(binary)
    # Smaller min_distance finds peaks in tightly packed clusters.
    min_distance = max(5, int(avg_diameter * 0.35))
    peaks = peak_local_max(distance, min_distance=min_distance, labels=binary)
    markers = np.zeros(distance.shape, dtype=np.int32)
    for i, (r, c) in enumerate(peaks, start=1):
        markers[r, c] = i
    markers = ndi.label(markers > 0)[0]

    if markers.max() > 0:
        labels = segmentation.watershed(-distance, markers, mask=binary)
    else:
        labels = rough_labels

    cleaned = np.zeros_like(labels, dtype=np.int32)
    cells: List[Dict] = []
    next_id = 1
    for region in measure.regionprops(labels, intensity_image=green_raw):
        if region.area < min_area or region.area > max_area:
            continue
        rr, cc = region.coords[:, 0], region.coords[:, 1]
        cleaned[rr, cc] = next_id
        cy, cx = region.centroid
        cells.append(
            {
                "cell_id": next_id,
                "x": float(cx),
                "y": float(cy),
                "area": int(region.area),
                "green_mean": float(region.mean_intensity),
                "green_max": float(region.max_intensity),
            }
        )
        next_id += 1

    auto_settings = {
        "green_threshold": round(otsu, 2),
        "estimated_min_area": int(min_area),
        "estimated_max_area": int(max_area),
        "estimated_cell_diameter_px": round(avg_diameter, 2),
        "positive_fraction_threshold": config.min_positive_fraction,
    }
    return cleaned, cells, auto_settings


def _channel_positive_stats(channel: np.ndarray, labels: np.ndarray) -> Dict:
    """Estimate marker background/threshold using the uploaded marker channel."""

    raw = channel.astype(np.float32)
    raw_u8 = normalize_u8(raw)
    background = cv2.GaussianBlur(raw_u8, (0, 0), 14)
    enhanced = cv2.subtract(raw_u8, background)
    enhanced = exposure.rescale_intensity(enhanced, out_range=(0, 255)).astype(np.uint8)

    valid = enhanced[labels > 0]
    if valid.size == 0:
        threshold = 255.0
        background_mean = 0.0
    else:
        try:
            threshold = float(filters.threshold_otsu(valid))
        except ValueError:
            threshold = float(np.percentile(valid, 95))
        # Avoid classifying weak haze as marker-positive.
        threshold = max(threshold, float(np.percentile(valid, 88)))
        background_mean = float(np.median(valid))

    return {"enhanced": enhanced, "threshold": threshold, "background_mean": background_mean}


def classify_green_cells(labels: np.ndarray, cells: List[Dict], red_img: np.ndarray, blue_img: np.ndarray, config: AutoConfig) -> Tuple[List[Dict], Dict]:
    red_stats = _channel_positive_stats(dominant_channel(red_img, "red"), labels)
    blue_stats = _channel_positive_stats(dominant_channel(blue_img, "blue"), labels)
    red_enhanced = red_stats["enhanced"]
    blue_enhanced = blue_stats["enhanced"]

    classified: List[Dict] = []
    totals = {
        "total_green": 0,
        "green_only": 0,
        "total_red": 0,
        "total_blue": 0,
        "total_overlap": 0,
    }

    for cell in cells:
        mask = labels == cell["cell_id"]
        area = int(mask.sum())
        if area == 0:
            continue

        red_values = red_enhanced[mask]
        blue_values = blue_enhanced[mask]

        red_positive_pixels = red_values > red_stats["threshold"]
        blue_positive_pixels = blue_values > blue_stats["threshold"]
        red_fraction = float(red_positive_pixels.mean())
        blue_fraction = float(blue_positive_pixels.mean())
        red_mean = float(red_values.mean())
        blue_mean = float(blue_values.mean())
        red_max = float(red_values.max())
        blue_max = float(blue_values.max())

        red_positive = (
            red_fraction >= config.min_positive_fraction
            and red_mean >= red_stats["background_mean"] * config.min_positive_signal_ratio
        )

        blue_positive = (
            blue_fraction >= config.min_positive_fraction
            and blue_mean >= blue_stats["background_mean"] * config.min_positive_signal_ratio
        )

        if red_positive and blue_positive:
            classification = "double_positive"
            totals["total_overlap"] += 1
        elif red_positive:
            classification = "red_positive"
        elif blue_positive:
            classification = "blue_positive"
        else:
            classification = "green_only"
            totals["green_only"] += 1

        if red_positive:
            totals["total_red"] += 1
        if blue_positive:
            totals["total_blue"] += 1
        totals["total_green"] += 1

        classified.append(
            {
                **cell,
                "area": area,
                "red_positive": bool(red_positive),
                "blue_positive": bool(blue_positive),
                "classification": classification,
                "red_mean": round(red_mean, 3),
                "blue_mean": round(blue_mean, 3),
                "red_max": round(red_max, 3),
                "blue_max": round(blue_max, 3),
                "red_positive_fraction": round(red_fraction, 4),
                "blue_positive_fraction": round(blue_fraction, 4),
            }
        )

    auto_settings = {
        "red_threshold": round(float(red_stats["threshold"]), 2),
        "blue_threshold": round(float(blue_stats["threshold"]), 2),
        "red_background_median": round(float(red_stats["background_mean"]), 2),
        "blue_background_median": round(float(blue_stats["background_mean"]), 2),
    }
    return classified, {**totals, **auto_settings}


_COLORS = {
    "green_only": (50, 220, 80),
    "red_positive": (255, 60, 60),
    "blue_positive": (60, 140, 255),
    "double_positive": (255, 210, 0),
}

_VIEW_FILTER: Dict[str, List[str]] = {
    "all": ["green_only", "red_positive", "blue_positive", "double_positive"],
    "double": ["double_positive"],
    "red_positive": ["red_positive", "double_positive"],
    "blue_positive": ["blue_positive", "double_positive"],
}

_VIEW_LEGEND: Dict[str, List[Tuple[str, str]]] = {
    "all": [
        ("Green only", "green_only"),
        ("Red+", "red_positive"),
        ("Blue+", "blue_positive"),
        ("Red+Blue overlap", "double_positive"),
    ],
    "double": [("Red+Blue overlap", "double_positive")],
    "red_positive": [("Red+", "red_positive"), ("Red+Blue overlap", "double_positive")],
    "blue_positive": [("Blue+", "blue_positive"), ("Red+Blue overlap", "double_positive")],
}


def make_overlay(green_img: np.ndarray, labels: np.ndarray, cells: List[Dict], output_path: str, view: str = "all") -> None:
    base = normalize_u8(dominant_channel(green_img, "green"))
    bg = cv2.cvtColor(base, cv2.COLOR_GRAY2RGB)

    shown_classes = set(_VIEW_FILTER.get(view, _VIEW_FILTER["all"]))
    all_classes = set(_VIEW_FILTER["all"])
    context_classes = all_classes - shown_classes

    # Keep background bright so underlying neuron morphology is visible.
    result = (bg * 0.85).astype(np.uint8)

    # Active cells: 2-px coloured ROI outline — no fill, neuron texture shows through.
    # Filtered views show ONLY the relevant cells so counts are easy to verify visually.
    for cell in cells:
        cls = cell["classification"]
        if cls not in shown_classes:
            continue
        color = _COLORS[cls]
        mask = (labels == cell["cell_id"]).astype(np.uint8)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(result, contours, -1, color, 2)

    # Legend — filled colour square + label.
    legend_items = _VIEW_LEGEND.get(view, _VIEW_LEGEND["all"])
    y0 = 24
    for i, (label_text, cls_key) in enumerate(legend_items):
        color = _COLORS[cls_key]
        y = y0 + i * 22
        cv2.rectangle(result, (10, y - 10), (22, y + 2), color, -1)
        cv2.putText(result, label_text, (30, y), cv2.FONT_HERSHEY_SIMPLEX, 0.48, color, 1, cv2.LINE_AA)

    cv2.imwrite(output_path, cv2.cvtColor(result, cv2.COLOR_RGB2BGR))


def _safe_percent(part: int, total: int) -> float:
    return round((part / total) * 100.0, 2) if total else 0.0


def analyze_images(green_path: str, red_path: str, blue_path: str, output_dir: str, config: AutoConfig | None = None) -> Dict:
    config = config or AutoConfig()
    os.makedirs(output_dir, exist_ok=True)

    green = read_image(green_path)
    red = resize_to_reference(read_image(red_path), green)
    blue = resize_to_reference(read_image(blue_path), green)

    labels, green_cells, green_settings = segment_green_cells(green, config)
    classified_cells, totals_and_marker_settings = classify_green_cells(labels, green_cells, red, blue, config)

    run_id = uuid.uuid4().hex[:10]
    csv_name = f"cells_{run_id}.csv"
    csv_path = os.path.join(output_dir, csv_name)

    pd.DataFrame(classified_cells).to_csv(csv_path, index=False)

    overlay_files: Dict[str, str] = {}
    for view in ("all", "double", "red_positive", "blue_positive"):
        name = f"overlay_{run_id}_{view}.png"
        make_overlay(green, labels, classified_cells, os.path.join(output_dir, name), view)
        overlay_files[view] = name

    total_green = int(totals_and_marker_settings["total_green"])
    total_red = int(totals_and_marker_settings["total_red"])
    total_blue = int(totals_and_marker_settings["total_blue"])
    total_overlap = int(totals_and_marker_settings["total_overlap"])
    green_only = int(totals_and_marker_settings["green_only"])

    double_positive_cells = [c for c in classified_cells if c["classification"] == "double_positive"]

    return {
        "total_green": total_green,
        "green_only": green_only,
        "total_red": total_red,
        "total_blue": total_blue,
        "total_overlap": total_overlap,
        "red_percent": _safe_percent(total_red, total_green),
        "blue_percent": _safe_percent(total_blue, total_green),
        "overlap_percent": _safe_percent(total_overlap, total_green),
        "green_only_percent": _safe_percent(green_only, total_green),
        "cells": classified_cells,
        "overlap_cells": double_positive_cells,
        "auto_settings": {**green_settings, **{k: v for k, v in totals_and_marker_settings.items() if k.endswith("threshold") or k.endswith("median")}},
        "overlay_file": overlay_files["all"],
        "overlay_files": overlay_files,
        "csv_file": csv_name,
    }
