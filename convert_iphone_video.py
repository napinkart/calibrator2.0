"""
Convert iPhone 11 videos from HEVC/H.265 to H.264/H.263 compatible format
for OpenCV processing.

iPhone 11 records video in HEVC/H.265 by default, but OpenCV 5.0.0 on Windows
has limited support for this codec. The calibrator system requires H.264,
MJPG/AVI, or similar codec.

Usage:
    python convert_iphone_video.py input_video.mov output_video.mp4
"""
import sys
import subprocess
from pathlib import Path
def convert_video(input_path, output_path):
    """Convert iPhone video to OpenCV-compatible format."""
    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.exists():
        print(f"ERROR: Input file '{input_path}' not found!")
        return False

    print(f"Converting {input_path.name} to OpenCV-compatible format...")
    print(f"Input: {input_path}")
    print(f"Output: {output_path}")

    # Method 1: Using ffmpeg (recommended)
    try:
        cmd = [
            'ffmpeg', '-y', '-i', str(input_path),
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
            '-c:a', 'aac', '-b:a', '128k',
            '-movflags', '+faststart',
            str(output_path)
        ]

        print(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            print("✓ Conversion successful!")
            return True
        else:
            print(f"✗ ffmpeg conversion failed:")
            print(result.stderr)

    except FileNotFoundError:
        print("ffmpeg not found. Trying alternative method...")

    # Method 2: Using HandBrakeCLI if available
    try:
        cmd = [
            'HandBrakeCLI', '-i', str(input_path),
            '-o', str(output_path),
            '--encoder', 'x264',
            '--rate', '30',
            '--quality', '20',
            '--format', 'MP4'
        ]

        print(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            print("✓ Conversion successful with HandBrakeCLI!")
            return True
        else:
            print(f"✗ HandBrakeCLI conversion failed:")
            print(result.stderr)

    except FileNotFoundError:
        pass

    # Method 3: Using ffmpeg with H.263 (older codec)
    try:
        cmd = [
            'ffmpeg', '-y', '-i', str(input_path),
            '-c:v', 'libopenh263', '-preset', 'fast',
            '-c:a', 'aac', '-b:a', '128k',
            str(output_path)
        ]

        print(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            print("✓ Conversion successful with H.263!")
            return True
        else:
            print(f"✗ H.263 conversion failed:")
            print(result.stderr)

    except Exception as e:
        print(f"✗ All conversion methods failed: {e}")
        return False

    # Method 4: Manual conversion suggestion
    if not output_path.exists():
        print("\n❌ Could not auto-convert. Try one of these manually:")
        print("\nOption 1: Use HandBrake (recommended)")
        print("  1. Download HandBrake from handbrake.fr")
        print("  2. Open input video, select 'MP4' format")
        print("  3. Choose x264 encoder, quality around 20")
        print("  4. Save as output file")

        print("\nOption 2: Use ffmpeg (if installed)")
        print(f"   ffmpeg -y -i \"{input_path}\" -c:v libx264 -preset fast -crf 23 \"{output_path}\"\n")

        return False

    return True
def main():
    if len(sys.argv) < 2:
        print("Usage: python convert_iphone_video.py <input_video> [output_video]")
        print("\nExample:")
        print("  python convert_iphone_video.py video.mov video_h264.mp4")
        print("\nIf output not specified, it will be created in the same directory")
        print("with '_h264' suffix.")
        return 1

    input_video = sys.argv[1]

    if len(sys.argv) >= 3:
        output_video = sys.argv[2]
    else:
        input_path = Path(input_video)
        output_video = input_path.parent / f"{input_path.stem}_h264{input_path.suffix}"

    if convert_video(input_video, output_video):
        print(f"\n✓ Success! Converted video is ready: {output_video}")
        print("You can now upload this video to the calibrator system.")
        return 0
    else:
        print(f"\n❌ Failed to convert video.")
        return 1
if __name__ == "__main__":
    sys.exit(main())