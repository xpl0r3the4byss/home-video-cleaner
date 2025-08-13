

#!/bin/bash

INPUT_DIR="./"
EXT="mov"

echo "Reviewing all .$EXT files in: $INPUT_DIR"
echo "Use your video player to determine correct aspect ratio for each."

shopt -s nullglob
for file in "$INPUT_DIR"/*."$EXT"; do
  base="${file%.*}"
  echo
  echo "===================================================="
  echo "Now reviewing: $file"
  echo "Please open this file in your preferred player (e.g. VLC) to preview it."
  echo "Then choose:"
  echo "  A = 4:3 (SAR 8:9)"
  echo "  B = 16:9 (SAR 40:33)"
  echo

  while true; do
    read -p "Enter choice for '$file' [A/B]: " choice
    case "$choice" in
      [Aa])
        sar="8/9"
        label="4x3"
        break
        ;;
      [Bb])
        sar="40/33"
        label="16x9"
        break
        ;;
      *)
        echo "Invalid input. Please enter A or B."
        ;;
    esac
  done

  temp_file="${base}_temp_${label}.mov"
  echo "Processing with SAR=$sar..."
  ffmpeg -loglevel error -i "$file" -vf "setsar=$sar" -c:v prores_ks -profile:v 3 -c:a copy "$temp_file"

  if [ ! -f "$temp_file" ]; then
    echo "❌ Failed to create output file. Skipping."
    continue
  fi

  orig_duration=$(ffprobe -v error -select_streams v:0 -show_entries format=duration -of csv=p=0 "$file")
  new_duration=$(ffprobe -v error -select_streams v:0 -show_entries format=duration -of csv=p=0 "$temp_file")

  orig_duration=${orig_duration%.*}
  new_duration=${new_duration%.*}

  if [ "$orig_duration" != "$new_duration" ]; then
    echo "❌ Duration mismatch: original=$orig_duration, new=$new_duration. Skipping deletion."
    continue
  fi

  expected_sar=$(echo "$sar" | sed 's|/|:|')
  actual_sar=$(ffprobe -v error -select_streams v:0 -show_entries stream=sample_aspect_ratio -of default=nw=1:nk=1 "$temp_file")

  if [ "$actual_sar" != "$expected_sar" ]; then
    echo "❌ SAR mismatch in output: expected $expected_sar, got $actual_sar. Skipping deletion."
    continue
  fi

  echo "✅ Verification passed. Replacing original file."
  mv "$temp_file" "$file"
done

echo
echo "✅ All files processed."