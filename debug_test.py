import sys
from pathlib import Path
from scenedetect import open_video, SceneManager
from scenedetect.detectors import ContentDetector

MAX_DURATION_SECONDS = 600  # 10 minutes

def run_scene_detection(video_path, threshold):
    video = open_video(str(video_path))
    fps = video.frame_rate
    max_frames = int(fps * MAX_DURATION_SECONDS)

    scene_manager = SceneManager()
    detector = ContentDetector(threshold=threshold, min_scene_len=15)
    scene_manager.add_detector(detector)

    scene_manager.detect_scenes(video, show_progress=True, duration=MAX_DURATION_SECONDS)

    scenes = scene_manager.get_scene_list()
    return scenes

def main():
    if len(sys.argv) < 2:
        print("Usage: python debug_test.py <video_file>")
        sys.exit(1)

    video_path = Path(sys.argv[1])
    if not video_path.is_file():
        print(f"File not found: {video_path}")
        sys.exit(1)

    thresholds = [0.1, 0.2, 0.3, 0.4, 0.5, 0.7, 0.85, 0.9, 1.0, 1.5, 2.0, 5.0, 10.0, 15.0]

    print(f"Running scene detection on first {MAX_DURATION_SECONDS} seconds of {video_path}")
    for thresh in thresholds:
        print(f"\nThreshold: {thresh}")
        scenes = run_scene_detection(video_path, thresh)
        print(f"Detected {len(scenes)} scenes:")
        for i, (start, end) in enumerate(scenes, start=1):
            print(f"  Scene {i}: {start.get_seconds():.3f}s to {end.get_seconds():.3f}s")

if __name__ == "__main__":
    main()