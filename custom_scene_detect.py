import cv2
import numpy as np
import os
import sys
import json
import re
from datetime import timedelta
from tqdm import tqdm

def calculate_histogram(frame):
    """
    Calculate the normalized color histogram for a frame.
    Uses HSV color space for better color segmentation.
    """
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1, 2], None, [8, 8, 8],
                        [0, 180, 0, 256, 0, 256])
    cv2.normalize(hist, hist)
    return hist.flatten()

def histogram_diff(hist1, hist2):
    """
    Compute a difference metric between two histograms.
    Using correlation distance: 1 - correlation coefficient.
    """
    correlation = cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)
    diff = 1 - correlation
    return diff

def seconds_to_iso8601(seconds):
    """
    Convert seconds (float) to ISO 8601 duration format (PT#H#M#S).
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    iso = "PT"
    if hours > 0:
        iso += f"{hours}H"
    if minutes > 0:
        iso += f"{minutes}M"
    iso += f"{secs:.3f}S"
    return iso

def detect_scenes(video_path, max_duration_sec=None, threshold=0.3, output_dir=None):
    """
    Detect scene cuts in the video by comparing histogram differences.
    Returns a list of scenes with start and end times in seconds.
    """
    spike_diffs = []

    input_basename = os.path.splitext(os.path.basename(video_path))[0]
    if output_dir is None:
        input_dir = os.path.dirname(video_path)
        base_output_dir = os.path.join(input_dir, input_basename)
        analysis_dir = os.path.join(base_output_dir, "analysis")
    else:
        analysis_dir = output_dir
    os.makedirs(analysis_dir, exist_ok=True)

    print(f"Opening video file: {video_path}")
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print("Error: Could not open video.")
        sys.exit(1)

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        print("Warning: FPS could not be determined, defaulting to 30.")
        fps = 30.0

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    video_duration = total_frames / fps
    print(f"Video FPS: {fps:.2f}, Total frames: {total_frames}, Duration: {video_duration:.2f} seconds")

    frame_idx = 0
    print(f"Processing video frames until end or max duration of {max_duration_sec} seconds")

    spike_times = []
    prev_hist = None
    # Initialize last_time for monotonicity check
    last_time = -1.0

    progress_bar = tqdm(total=total_frames, desc="🔍 Analyzing frames", unit="frame")

    while True:
        ret, frame = cap.read()
        if not ret:
            progress_bar.write(f"\nEnd of video or read error at frame {frame_idx}.")
            break

        curr_time = frame_idx / fps

        if max_duration_sec is not None and curr_time > max_duration_sec:
            progress_bar.write(f"\nReached max duration at frame {frame_idx} ({curr_time:.2f}s). Stopping.")
            break

        if curr_time < last_time:
            progress_bar.write(f"\nWarning: Non-monotonic timestamp detected at frame {frame_idx}: {curr_time:.3f}s < last {last_time:.3f}s")

        last_time = curr_time

        curr_hist = calculate_histogram(frame)

        if prev_hist is not None:
            diff = histogram_diff(prev_hist, curr_hist)
            if diff > threshold:
                spike_times.append(curr_time)
                spike_diffs.append(diff)
                # progress_bar.write(f"\nDetected spike at frame {frame_idx}, time {curr_time:.3f}s, diff={diff:.4f}")
        else:
            progress_bar.write(f"Processing first frame at time {curr_time:.3f}s")

        prev_hist = curr_hist
        frame_idx += 1
        progress_bar.update(1)

    progress_bar.close()

    cap.release()

    print(f"\nAll detected spikes (pre-sort): {spike_times}")

    spike_times = sorted(spike_times)
    print(f"All detected spikes (sorted): {spike_times}")

    scenes = []
    scene_start_time = 0.0

    for spike_time in spike_times:
        if spike_time <= scene_start_time:
            print(f"Ignored spike at {spike_time:.3f}s because it is not after last scene end {scene_start_time:.3f}s")
            continue

        duration = spike_time - scene_start_time
        if duration >= 2.0:
            scenes.append({
                "start": scene_start_time,
                "end": spike_time
            })
            print(f"Scene cut accepted: start={scene_start_time:.3f}s, end={spike_time:.3f}s, duration={duration:.3f}s")
            scene_start_time = spike_time
        else:
            print(f"Ignored short spike at {spike_time:.3f}s (duration={duration:.3f}s)")

    # Add last scene till end of processed video segment
    scenes.append({
        "start": scene_start_time,
        "end": min(video_duration, max_duration_sec) if max_duration_sec is not None else video_duration
    })

    # Print final scene cut accepted message before top spikes
    end_time = min(video_duration, max_duration_sec) if max_duration_sec is not None else video_duration
    print(f"Final scene cut accepted: start={scene_start_time:.3f}s, end={end_time:.3f}s, duration={end_time - scene_start_time:.3f}s")
    # Print top 10 histogram difference spikes
    print("\nTop 10 histogram difference spikes:")
    top_spikes = sorted(zip(spike_times, spike_diffs), key=lambda x: x[1], reverse=True)[:10]
    for t, d in top_spikes:
        print(f"  Time {t:.3f}s - diff = {d:.4f}")

    # Save histogram diffs to CSV
    diff_output_path = os.path.join(analysis_dir, f"{input_basename}_diffs.csv")
    with open(diff_output_path, "w") as f:
        f.write("time_sec,diff\n")
        for t, d in zip(spike_times, spike_diffs):
            f.write(f"{t:.3f},{d:.6f}\n")
    print(f"Histogram difference CSV saved to: {diff_output_path}")

    # Enforce all start/end values are floats
    scenes = [
        {
            "start": float(scene["start"]),
            "end": float(scene["end"])
        }
        for scene in scenes
    ]
    scenes = sorted(scenes, key=lambda s: s["start"])
    return scenes

def save_scenes_json(scenes, video_path, output_dir=None):
    """
    Save the detected scenes to a JSON file in 'output' directory.
    Filename: [video_basename]_custom_scenes.json
    """
    if output_dir is None:
        json_output_dir = os.path.join(os.path.dirname(video_path), os.path.splitext(os.path.basename(video_path))[0], "analysis")
    else:
        json_output_dir = output_dir
    os.makedirs(json_output_dir, exist_ok=True)
    base_name = f"clip_{int(os.path.splitext(os.path.basename(video_path))[0].split('_')[-1]) + 1:02d}"
    if base_name == "clip_00":
        base_name = "clip_01"
    output_path = os.path.join(json_output_dir, f"{base_name}_custom_scenes.json")

    scenes_serializable = [
        {
            "start": seconds_to_iso8601(scene["start"]),
            "end": seconds_to_iso8601(scene["end"])
        }
        for scene in scenes
    ]
    with open(output_path, "w") as f:
        json.dump(scenes_serializable, f, indent=4)

    print(f"Scene list saved to: {output_path}")

def print_summary(scenes):
    """
    Print a summary of detected scenes.
    """
    print("\nScene Detection Summary:")
    print(f"Total scenes detected: {len(scenes)}")
    for idx, scene in enumerate(scenes):
        print(f"  Scene {idx+1}: Start = {scene['start']}, End = {scene['end']}")

def iso8601_to_seconds(iso_str):
    """
    Convert ISO 8601 duration string (PT#H#M#S) to total seconds as float.
    """
    pattern = re.compile(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?')
    match = pattern.match(iso_str)
    if not match:
        raise ValueError(f"Invalid ISO 8601 duration format: {iso_str}")
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = float(match.group(3) or 0)
    total_seconds = hours * 3600 + minutes * 60 + seconds
    return total_seconds

def print_scene_summary_from_json(json_path):
    """
    Read scene JSON file and print human-readable scene summary.
    """
    with open(json_path, 'r') as f:
        scenes = json.load(f)

    print(f"\nScene summary for {json_path}:")
    for i, scene in enumerate(scenes):
        start_sec = iso8601_to_seconds(scene['start'])
        end_sec = iso8601_to_seconds(scene['end'])
        duration_sec = end_sec - start_sec
        start_td = str(timedelta(seconds=start_sec))
        end_td = str(timedelta(seconds=end_sec))
        print(f"Scene {i+1}: Start = {start_td} ({start_sec:.3f}s), "
              f"End = {end_td} ({end_sec:.3f}s), Duration = {duration_sec:.3f}s")

def main():
    if len(sys.argv) < 2:
        print("Usage: python custom_scene_detect.py <video_file_path> [scene_json_file]")
        sys.exit(1)

    video_path = sys.argv[1]

    if len(sys.argv) == 3 and sys.argv[2].endswith('.json'):
        # If second argument is JSON file, print scene summary and exit
        print_scene_summary_from_json(sys.argv[2])
        sys.exit(0)

    # Configurable parameters
    MAX_DURATION_SEC = None  # Process the entire video
    THRESHOLD = .35      # Histogram difference threshold for scene cuts

    print("Starting custom scene detection...")
    scenes = detect_scenes(video_path, max_duration_sec=MAX_DURATION_SEC, threshold=THRESHOLD)
    save_scenes_json(scenes, video_path)
    print_summary(scenes)
    print("Done.")

if __name__ == "__main__":
    main()
