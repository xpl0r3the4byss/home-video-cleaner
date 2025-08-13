import subprocess
import json
from pathlib import Path
from typing import List, Dict
from config import SCENE_THRESHOLD_LOW
from utils import verbose_log

def detect_scene_changes_low_threshold(
    input_file: Path,
    threshold: float = SCENE_THRESHOLD_LOW
) -> List[float]:
    """
    Run FFmpeg scene detection filter with a low threshold on input_file.
    Returns a sorted list of scene change timestamps (seconds).
    """
    cmd = [
        "ffmpeg",
        "-hide_banner", "-loglevel", "error",
        "-i", str(input_file),
        "-filter:v", f"select='gt(scene,{threshold})',showinfo",
        "-f", "null",
        "-"
    ]
    verbose_log(f"Running FFmpeg scene detection with threshold {threshold}:\n{' '.join(cmd)}")
    proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, universal_newlines=True)
    scene_timestamps = []

    for line in proc.stderr:
        if "pts_time:" in line:
            try:
                pts_str = line.split("pts_time:")[1].split(" ")[0]
                timestamp = float(pts_str)
                scene_timestamps.append(timestamp)
            except (IndexError, ValueError):
                continue

    proc.wait()
    verbose_log(f"Detected {len(scene_timestamps)} scene change timestamps at low threshold")
    scene_timestamps = sorted(set(scene_timestamps))
    return scene_timestamps

def get_video_duration_and_frames(input_file: Path) -> Dict[str, float]:
    """
    Uses ffprobe to get the duration in seconds and total number of frames.
    Returns dict with keys 'duration' and 'frames'.
    """
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "format=duration",
        "-show_entries", "stream=nb_frames",
        "-of", "json",
        str(input_file)
    ]
    verbose_log(f"Running ffprobe to get video info:\n{' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {input_file}")
    info = json.loads(result.stdout)
    duration = float(info["format"]["duration"])
    nb_frames_str = info["streams"][0].get("nb_frames", "0")
    try:
        frames = int(nb_frames_str)
    except ValueError:
        frames = 0
    verbose_log(f"Video duration: {duration} seconds, frames: {frames}")
    return {"duration": duration, "frames": frames}

def build_scene_json(
    input_file: Path,
    threshold: float,
    scene_timestamps: List[float],
    video_info: Dict[str, float]
) -> Dict:
    """
    Builds a JSON-compatible dict with scene info:
    - total_scenes
    - duration
    - scenes: list of scene dicts with start_time, end_time, start_frame, end_frame
    """
    duration = video_info["duration"]
    frames = video_info["frames"]
    scenes = []
    prev = 0.0
    for i, ts in enumerate(scene_timestamps):
        scenes.append({
            "scene_number": i+1,
            "start_time": f"{prev:.3f}",
            "end_time": f"{ts:.3f}",
            "start_frame": int(prev / duration * frames) if frames > 0 else None,
            "end_frame": int(ts / duration * frames) if frames > 0 else None
        })
        prev = ts
    scenes.append({
        "scene_number": len(scene_timestamps)+1,
        "start_time": f"{prev:.3f}",
        "end_time": f"{duration:.3f}",
        "start_frame": int(prev / duration * frames) if frames > 0 else None,
        "end_frame": frames if frames > 0 else None
    })
    return {
        "video_file": str(input_file),
        "duration": f"{duration:.3f}",
        "threshold": threshold,
        "total_scenes": len(scenes),
        "scenes": scenes
    }

def export_scene_json(
    scene_json: Dict,
    output_path: Path
) -> None:
    """
    Saves scene_json dict to output_path as pretty-printed JSON.
    """
    with open(output_path, "w") as f:
        json.dump(scene_json, f, indent=2)
    verbose_log(f"Exported scene JSON to {output_path}")

def run_low_threshold_scene_detection(
    input_file: Path,
    output_json: Path,
    threshold: float = SCENE_THRESHOLD_LOW
) -> None:
    """
    Runs low-threshold scene detection on input_file and writes scene metadata JSON.
    """
    verbose_log(f"Running low-threshold scene detection on {input_file}")
    scene_timestamps = detect_scene_changes_low_threshold(input_file, threshold)
    video_info = get_video_duration_and_frames(input_file)
    scene_json = build_scene_json(input_file, threshold, scene_timestamps, video_info)
    export_scene_json(scene_json, output_json)
    verbose_log(f"Completed low-threshold scene detection for {input_file}")