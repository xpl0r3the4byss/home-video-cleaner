

import sys
from pathlib import Path
import subprocess
import shutil
import tempfile

def concat_folder(folder_path: str):
    folder = Path(folder_path)
    if not folder.exists() or not folder.is_dir():
        print(f"Error: {folder_path} is not a valid directory.")
        return

    # Copy folder to /tmp/home-video-cleaner/<original_folder_name>
    local_temp_root = Path(tempfile.gettempdir()) / "home-video-cleaner"
    local_folder = local_temp_root / folder.name
    if local_folder.exists():
        shutil.rmtree(local_folder)
    shutil.copytree(folder, local_folder)

    mov_files = sorted(local_folder.glob("*.mov"))
    if not mov_files:
        print(f"No .mov files found in {folder_path}")
        return

    list_file_path = local_folder / "file_list.txt"
    with list_file_path.open("w") as f:
        for clip in mov_files:
            f.write(f"file '{clip.resolve()}'\n")

    output_filename = local_folder.with_suffix(".mov").name
    output_path = local_folder.with_suffix(".mov")
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(list_file_path),
        "-c", "copy", str(output_path)
    ]

    print(f"Combining {len(mov_files)} clips into: {output_filename}")
    subprocess.run(cmd, check=True)
    print("✅ Done!")

    # Move final .mov to original location under "finals" subdirectory
    finals_dir = folder / "finals"
    finals_dir.mkdir(exist_ok=True)
    final_output_path = finals_dir / output_filename
    shutil.move(str(output_path), final_output_path)

    shutil.rmtree(local_folder)
    print(f"Moved final output to {final_output_path}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python concat_folder.py <folder_of_clips>")
        sys.exit(1)
    concat_folder(sys.argv[1])