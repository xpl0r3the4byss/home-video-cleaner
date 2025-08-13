import sys
import traceback
from pathlib import Path
# from blue_trim import detect_non_blue_segments
from segment_extractor import extract_segments
from custom_scene_detect import detect_scenes, save_scenes_json
from config import OUTPUT_DIR, HIGH_THRESHOLD, LOW_THRESHOLD, FRAME_RATE_DEFAULT
import sys
try:
    from tqdm import tqdm
except ImportError:
    tqdm = None
    def tqdm_write(msg):
        print(msg, file=sys.stderr)
else:
    def tqdm_write(msg):
        tqdm.write(msg)
from utils import verbose_log
import subprocess
import json

def process_file(input_file: Path):
    print("PROCESS FILE STARTED")
    verbose_log(f"\n🔵 Starting processing for: {input_file}")
    import shutil

    original_input_path = input_file
    desktop_dir = Path.home() / "Desktop" / "home_video_cleaner"
    working_dir = desktop_dir / input_file.stem
    working_dir.mkdir(parents=True, exist_ok=True)

    from_file_status_path = working_dir / "status.txt"
    prior_status = from_file_status_path.read_text().strip() if from_file_status_path.exists() else None

    if prior_status == "plex_done":
        verbose_log("✅ All processing already completed for this file.")
        return
    elif prior_status == "concatenated":
        verbose_log("🔁 Skipping to Plex conversion and copy-back steps.")
        # Ensure input_file and derived paths point to working_dir
        input_file = working_dir / input_file.name
    elif prior_status == "scenes_extracted":
        verbose_log("⏩ Skipping input copy and scene detection.")
        # Ensure input_file and derived paths point to working_dir
        input_file = working_dir / input_file.name
    else:
        # Prompt for aspect ratio choice before copying input file
        aspect_ratio_choice_path = working_dir / "aspect_choice.txt"
        if not aspect_ratio_choice_path.exists():
            print("\n📺 Please specify the display aspect ratio for this video:")
            print("   A) 4:3")
            print("   B) Anamorphic 16:9")
            choice = input("Enter choice (A/B): ").strip().upper()
            while choice not in ("A", "B"):
                choice = input("Invalid choice. Please enter A or B: ").strip().upper()
            aspect_ratio_choice_path.write_text(choice)
        else:
            choice = aspect_ratio_choice_path.read_text().strip().upper()

        local_input_file = working_dir / input_file.name

        if local_input_file.exists() and local_input_file.stat().st_size == input_file.stat().st_size:
            verbose_log(f"📥 Input file already exists in working directory with matching size: {local_input_file}")
        else:
            if local_input_file.exists():
                verbose_log(f"⚠️ Size mismatch or previous copy detected. Removing: {local_input_file}")
                local_input_file.unlink()
            verbose_log(f"📥 Copying input file to working directory: {local_input_file}")
            from tqdm import tqdm
            def copy_file_with_progress(src, dst):
                total_size = src.stat().st_size
                with tqdm(total=total_size, unit='B', unit_scale=True, desc="📥 Copying input file") as pbar:
                    with src.open('rb') as fsrc, dst.open('wb') as fdst:
                        while True:
                            buf = fsrc.read(1024 * 1024)
                            if not buf:
                                break
                            fdst.write(buf)
                            pbar.update(len(buf))

            copy_file_with_progress(input_file, local_input_file)

        input_file = local_input_file

    # Ensure aspect ratio choice is available regardless of branch
    aspect_ratio_choice_path = working_dir / "aspect_choice.txt"
    if aspect_ratio_choice_path.exists():
        choice = aspect_ratio_choice_path.read_text().strip().upper()
    else:
        # Fallback default if missing (shouldn't happen)
        choice = "A"

    stem = input_file.stem
    # Always use working_dir for output_clips_dir after resuming or copying
    output_clips_dir = working_dir / stem / "clips"
    # output_clips_dir.mkdir(parents=True, exist_ok=True)  # Don't create [input_stem] dir here; will be handled at final copy

    try:
        clip_files = [input_file]

        base_output_dir = input_file.parent / stem
        analysis_dir = base_output_dir / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)

        if prior_status not in ("scenes_extracted", "concatenated", "plex_done"):
            # Pass 2 and 3: Scene splitting and low-threshold JSON export
            for clip_index, clip_file in enumerate(clip_files):
                verbose_log(f"Analyzing frames in {clip_file.name}...")
                verbose_log(f"Pass 2: High-threshold scene splitting on {clip_file.name}...")
                scene_timestamps = detect_scenes(clip_file, threshold=HIGH_THRESHOLD, output_dir=analysis_dir)
                verbose_log("Pass 2: Detected scene timestamps:")
                for i, s in enumerate(scene_timestamps):
                    try:
                        start = float(s["start"])
                        end = float(s["end"])
                        duration = end - start
                        verbose_log(f"  Scene {i:02d}: start={start:.3f}  end={end:.3f}  duration={duration:.3f}")
                    except Exception as e:
                        verbose_log(f"  Scene {i:02d}: Invalid timestamps - {s} ({e})")
                scene_ranges = [
                    (s["start"], s["end"])
                    for s in scene_timestamps
                    if isinstance(s["start"], (int, float)) and isinstance(s["end"], (int, float)) and s["end"] - s["start"] >= 0.25
                ]
                tqdm_write(f"🔪 Splitting {clip_file.name}")
                scene_files = extract_segments(
                    clip_file,
                    scene_ranges,
                    output_clips_dir,
                    prefix=f"clip_{clip_index + 1:02d}_scene"
                )
            from_file_status_path.write_text("scenes_extracted")
        else:
            scene_files = list(output_clips_dir.glob("clip_*_scene*.mov"))

        if prior_status not in ("concatenated", "plex_done"):
            print("\n✅ All scenes have been clipped.")
            print("📂 Please organize them into folders within this directory:")
            print(f"   {output_clips_dir}")
            input("⏸️  When ready, press ENTER to continue and concatenate each folder into a final video...\n")

            from concat_folder import concat_folder

            for subfolder in sorted(output_clips_dir.iterdir()):
                if subfolder.is_dir():
                    print(f"▶️  Concatenating clips in folder: {subfolder.name}")
                    try:
                        concat_folder(subfolder)
                        # Transcode to H.265 with user-chosen aspect ratio for Plex
                        local_concat_path = subfolder / f"{subfolder.name}_concatenated.mov"
                        plex_output_path = subfolder / f"{subfolder.name}.mp4"
                        if local_concat_path.exists():
                            def get_display_resolution(mov_file, choice):
                                import subprocess
                                probe_cmd = [
                                    "ffprobe",
                                    "-v", "error",
                                    "-select_streams", "v:0",
                                    "-show_entries", "stream=width,height,display_aspect_ratio,sample_aspect_ratio",
                                    "-of", "json",
                                    str(mov_file)
                                ]
                                try:
                                    result = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
                                    info = json.loads(result.stdout)
                                    stream = info["streams"][0]
                                    sar = stream.get("sample_aspect_ratio", "1:1")
                                    width = stream.get("width", 720)
                                    height = stream.get("height", 480)
                                    num, den = map(int, sar.split(":"))
                                    if den == 0:
                                        return width, height  # fallback
                                    par = num / den
                                    dar = (width * par) / height
                                    # Override with user-provided aspect choice
                                    if choice == "A":
                                        return 640, 480  # 4:3
                                    elif choice == "B":
                                        return 854, 480  # anamorphic 16:9
                                    else:
                                        return 640, 480  # fallback to 4:3 if invalid
                                except Exception as e:
                                    verbose_log(f"⚠️ ffprobe failed on {mov_file}: {e}")
                                    return 720, 480
                            out_width, out_height = get_display_resolution(local_concat_path, choice)
                            ffmpeg_command = [
                                "ffmpeg",
                                "-i", str(local_concat_path),
                                "-vf", f"scale={out_width}:{out_height}",
                                "-c:v", "libx265",
                                "-pix_fmt", "yuv420p",
                                "-tag:v", "hvc1",
                                "-crf", "23",
                                "-preset", "slow",
                                "-c:a", "aac",
                                "-b:a", "192k",
                                str(plex_output_path)
                            ]
                            max_retries = 3
                            retry_count = 0
                            success = False
                            while retry_count < max_retries and not success:
                                try:
                                    subprocess.run(ffmpeg_command, check=True)
                                    if plex_output_path.exists() and plex_output_path.stat().st_size > 0:
                                        success = True
                                        verbose_log(f"🎞️  Created Plex-optimized version: {plex_output_path}")
                                    else:
                                        retry_count += 1
                                        verbose_log(f"⚠️ Plex version creation failed (attempt {retry_count}/{max_retries})")
                                except subprocess.CalledProcessError as e:
                                    retry_count += 1
                                    if retry_count < max_retries:
                                        verbose_log(f"⚠️ Error creating Plex version for {subfolder.name}, retrying ({retry_count}/{max_retries}): {e}")
                                    else:
                                        verbose_log(f"❌ Error creating Plex version for {subfolder.name} after {max_retries} attempts: {e}")
                            if not success:
                                raise Exception(f"Failed to create Plex version for {subfolder.name} after {max_retries} attempts")
                    except Exception as e:
                        verbose_log(f"❌ Error while concatenating {subfolder.name}: {e}")

            from_file_status_path.write_text("concatenated")

            # Create Plex-optimized versions of all final .mov files (including loose ones)
            from tqdm import tqdm
            def get_display_resolution(mov_file, choice):
                import subprocess
                probe_cmd = [
                    "ffprobe",
                    "-v", "error",
                    "-select_streams", "v:0",
                    "-show_entries", "stream=width,height,display_aspect_ratio,sample_aspect_ratio",
                    "-of", "json",
                    str(mov_file)
                ]
                try:
                    result = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
                    info = json.loads(result.stdout)
                    stream = info["streams"][0]
                    sar = stream.get("sample_aspect_ratio", "1:1")
                    width = stream.get("width", 720)
                    height = stream.get("height", 480)
                    num, den = map(int, sar.split(":"))
                    if den == 0:
                        return width, height  # fallback
                    par = num / den
                    dar = (width * par) / height
                    # Override with user-provided aspect choice
                    if choice == "A":
                        return 640, 480  # 4:3
                    elif choice == "B":
                        return 854, 480  # anamorphic 16:9
                    else:
                        return 640, 480  # fallback to 4:3 if invalid
                except Exception as e:
                    verbose_log(f"⚠️ ffprobe failed on {mov_file}: {e}")
                    return 720, 480

            def get_duration_seconds(mov_file):
                import subprocess
                probe_cmd = [
                    "ffprobe",
                    "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(mov_file)
                ]
                try:
                    result = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
                    duration_str = result.stdout.strip()
                    return float(duration_str)
                except Exception as e:
                    verbose_log(f"⚠️ ffprobe failed to get duration on {mov_file}: {e}")
                    return 1.0

            # All .mov files in any [*/finals/*.mov] under output_clips_dir
            final_mov_files = list(output_clips_dir.glob("*/finals/*.mov"))
            for mov_file in final_mov_files:
                tqdm_write(f"🎞️ Transcoding to Plex: {mov_file.name}")
                plex_output_path = mov_file.with_suffix(".mp4")
                out_width, out_height = get_display_resolution(mov_file, choice)
                duration_in_seconds = get_duration_seconds(mov_file)
                ffmpeg_command = [
                    "ffmpeg",
                    "-i", str(mov_file),
                    "-vf", f"scale={out_width}:{out_height}",
                    "-c:v", "libx265",
                    "-pix_fmt", "yuv420p",
                    "-tag:v", "hvc1",
                    "-crf", "23",
                    "-preset", "slow",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-progress", "pipe:1",
                    "-nostats",
                    str(plex_output_path)
                ]
                import re
                import shlex
                with tqdm(total=duration_in_seconds, desc=f"🎞️ {mov_file.stem}", unit='s') as pbar:
                    try:
                        proc = subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True)
                        time_pattern = re.compile(r'time=(\d+):(\d+):(\d+)\.(\d+)')
                        seconds_pattern = re.compile(r'time=(\d+\.\d+)')
                        last_seconds = 0.0
                        for line in proc.stdout:
                            # ffmpeg -progress output: key=value
                            if line.startswith("out_time="):
                                # out_time=00:01:23.45
                                val = line.strip().split('=')[1]
                                try:
                                    h, m, s = val.split(':')
                                    sec = float(h) * 3600 + float(m) * 60 + float(s)
                                    pbar.update(sec - last_seconds)
                                    last_seconds = sec
                                except Exception:
                                    pass
                            elif line.startswith("progress=") and "end" in line:
                                # End of progress
                                if last_seconds < duration_in_seconds:
                                    pbar.update(duration_in_seconds - last_seconds)
                        proc.wait()
                        pbar.close()
                        if proc.returncode == 0:
                            verbose_log(f"🎞️  Created Plex-optimized version: {plex_output_path}")
                        else:
                            verbose_log(f"❌ Error creating Plex version for {mov_file.name}: ffmpeg exited with code {proc.returncode}")
                    except Exception as e:
                        pbar.close()
                        verbose_log(f"❌ Error creating Plex version for {mov_file.name}: {e}")

            # Also create Plex-optimized versions of loose .mov files in clips directory
            loose_mov_files = list(output_clips_dir.glob("*.mov"))
            for mov_file in loose_mov_files:
                tqdm_write(f"🎞️ Transcoding to Plex: {mov_file.name}")
                plex_output_path = mov_file.with_suffix(".mp4")
                out_width, out_height = get_display_resolution(mov_file, choice)
                duration_in_seconds = get_duration_seconds(mov_file)
                ffmpeg_command = [
                    "ffmpeg",
                    "-i", str(mov_file),
                    "-vf", f"scale={out_width}:{out_height}",
                    "-c:v", "libx265",
                    "-pix_fmt", "yuv420p",
                    "-tag:v", "hvc1",
                    "-crf", "23",
                    "-preset", "slow",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-progress", "pipe:1",
                    "-nostats",
                    str(plex_output_path)
                ]
                import re
                import shlex
                max_retries = 3
                retry_count = 0
                success = False
                while retry_count < max_retries and not success:
                    with tqdm(total=duration_in_seconds, desc=f"🎞️ {mov_file.stem} (attempt {retry_count + 1}/{max_retries})", unit='s') as pbar:
                        try:
                            proc = subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True)
                            time_pattern = re.compile(r'time=(\d+):(\d+):(\d+)\.(\d+)')
                            seconds_pattern = re.compile(r'time=(\d+\.\d+)')
                            last_seconds = 0.0
                            for line in proc.stdout:
                                if line.startswith("out_time="):
                                    val = line.strip().split('=')[1]
                                    try:
                                        h, m, s = val.split(':')
                                        sec = float(h) * 3600 + float(m) * 60 + float(s)
                                        pbar.update(sec - last_seconds)
                                        last_seconds = sec
                                    except Exception:
                                        pass
                                elif line.startswith("progress=") and "end" in line:
                                    if last_seconds < duration_in_seconds:
                                        pbar.update(duration_in_seconds - last_seconds)
                            proc.wait()
                            pbar.close()
                            if proc.returncode == 0 and plex_output_path.exists() and plex_output_path.stat().st_size > 0:
                                verbose_log(f"🎞️  Created Plex-optimized version: {plex_output_path}")
                                success = True
                            else:
                                retry_count += 1
                                if retry_count < max_retries:
                                    verbose_log(f"⚠️ Error creating Plex version for {mov_file.name}, retrying ({retry_count}/{max_retries})")
                                else:
                                    verbose_log(f"❌ Error creating Plex version for {mov_file.name} after {max_retries} attempts")
                                    raise Exception(f"Failed to create Plex version for {mov_file.name} after {max_retries} attempts")
                        except Exception as e:
                            pbar.close()
                            retry_count += 1
                            if retry_count < max_retries:
                                verbose_log(f"⚠️ Error creating Plex version for {mov_file.name}, retrying ({retry_count}/{max_retries}): {e}")
                                continue
                            verbose_log(f"❌ Error creating Plex version for {mov_file.name} after {max_retries} attempts: {e}")
                            raise

            from_file_status_path.write_text("plex_done")
        else:
            print("\n✅ Skipping concatenation step as already done.")

        if prior_status != "plex_done":
            # Plex conversion is now handled after concatenation above.
            pass
        else:
            print("\n✅ Skipping Plex conversion step as already done.")

        # Move results back to original location
        final_output_dir = original_input_path.parent
        final_output_dir.mkdir(parents=True, exist_ok=True)

        for subfolder in sorted(output_clips_dir.iterdir()):
            if subfolder.is_dir():
                final_output_path = final_output_dir / f"{subfolder.name}.mov"
                local_concat_path = subfolder / f"{subfolder.name}_concatenated.mov"
                if local_concat_path.exists():
                    shutil.move(str(local_concat_path), final_output_path)
                    verbose_log(f"📤 Moved final video to: {final_output_path}")

        # Move entire working dir to original input folder for archival/debug purposes
        archived_temp_dir = original_input_path.parent / f"{original_input_path.stem}"
        archived_temp_dir.mkdir(parents=True, exist_ok=True)
        if archived_temp_dir.exists():
            shutil.rmtree(archived_temp_dir)
        import os
        from tqdm import tqdm
        def copy_with_progress(src_dir, dst_root):
            archive_files = []
            plex_files = []
            for root, dirs, files in os.walk(src_dir):
                for file in files:
                    full_path = Path(root) / file
                    rel_path = full_path.relative_to(src_dir)
                    suffix = full_path.suffix.lower()

                    if suffix not in ['.mov', '.mp4']:
                        continue

                    try:
                        # Match loose files in clips/
                        if rel_path.match("clips/*.mov"):
                            dst_path = dst_root / "Archive" / file
                            archive_files.append((full_path, dst_path))
                        elif rel_path.match("clips/*.mp4"):
                            dst_path = dst_root / "Plex" / file
                            plex_files.append((full_path, dst_path))
                        # Match finals files in clips/*/finals/
                        elif rel_path.match("clips/*/finals/*.mov"):
                            dst_path = dst_root / "Archive" / file
                            archive_files.append((full_path, dst_path))
                        elif rel_path.match("clips/*/finals/*.mp4"):
                            dst_path = dst_root / "Plex" / file
                            plex_files.append((full_path, dst_path))
                    except Exception as e:
                        verbose_log(f"⚠️ Skipped {rel_path}: {e}")

            all_files = archive_files + plex_files
            verbose_log(f"📦 Total files queued for copy: {len(all_files)}")

            if not all_files:
                return False

            for src, dst in tqdm(all_files, desc="📁 Copying working directory"):
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                verbose_log(f"📋 Copied: {src} -> {dst}")

            return True

        copied = copy_with_progress(working_dir, archived_temp_dir)
        # Verify Plex files exist before cleanup
        plex_success = True
        for plex_file in archived_temp_dir.glob("**/Plex/*.mp4"):
            if not plex_file.exists() or plex_file.stat().st_size == 0:
                plex_success = False
                verbose_log(f"❌ Missing or empty Plex file: {plex_file}")

        if copied and plex_success:
            verbose_log(f"📁 Copied working dir to: {archived_temp_dir}")
        else:
            error_msg = []
            if not copied:
                error_msg.append("No files copied to input source location")
            if not plex_success:
                error_msg.append("Missing or invalid Plex files")
            verbose_log(f"❌ {'; '.join(error_msg)}; skipping cleanup.")
            verbose_log(f"📂 Expected files in: {archived_temp_dir}")
            return

        # Only clean up after all moves complete
        verbose_log(f"🧹 Cleaning up working dir: {working_dir}")
        shutil.rmtree(working_dir, ignore_errors=True)

    except Exception as e:
        verbose_log(f"Error processing file {input_file}: {e}")
        verbose_log(traceback.format_exc())

def main():
    print("MAIN FUNCTION STARTED")
    verbose_log("home_video_cleaner started")
    if len(sys.argv) < 2:
        print("Usage: python main.py <input_file_or_directory>")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    verbose_log(f"Input path: {input_path}")

    if input_path.is_file():
        process_file(input_path)
    elif input_path.is_dir():
        mov_files = sorted(input_path.glob("*.mov"))
        if not mov_files:
            print("No .mov files found in directory.")
            sys.exit(1)
        for f in mov_files:
            process_file(f)
    else:
        print("Invalid input path.")
        sys.exit(1)

if __name__ == "__main__":
    main()
