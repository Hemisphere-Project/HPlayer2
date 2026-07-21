#!/bin/bash
# Blackout utility: fill a Linux framebuffer device with a solid color
# Usage: blackout.sh [COLOR] [FBDEV]
# COLOR: hex color in RRGGBB or #RRGGBB format (default: 000000 = black)
#        Note: if using # prefix, quote the argument: '#FF0000' or "#FF0000"
# FBDEV: framebuffer device (default: /dev/fb0)
# Examples:
#   blackout.sh              # black screen on /dev/fb0
#   blackout.sh FF0000       # red screen on /dev/fb0
#   blackout.sh '#00FF00'    # green screen on /dev/fb0 (quoted for # prefix)
#   blackout.sh 00FF00 /dev/fb1  # green screen on /dev/fb1

set -eu

COLOR="${1:-000000}"
FBDEV="${2:-/dev/fb0}"

# No framebuffer node on this platform (e.g. x86 DRM-only, like the N100
# minis): nothing to black out. Exit 0 — the hplayer2 launcher calls this
# under `set -e` and must not die on fbdev-less hardware.
if [ ! -e "$FBDEV" ]; then
	echo "Blackout: no framebuffer device $FBDEV — skipping" >&2
	exit 0
fi

# Strip leading # from color if present
COLOR="${COLOR#\#}"

fbname=$(basename "$FBDEV")
sysdir="/sys/class/graphics/$fbname"

# Try to read virtual_size (WIDTH,HEIGHT) from sysfs, fall back to fbset if needed
WIDTH=0
HEIGHT=0
if [ -r "$sysdir/virtual_size" ]; then
	vs=$(cat "$sysdir/virtual_size")
	# virtual_size is usually comma-separated 'WIDTH,HEIGHT'
	if [[ "$vs" == *,* ]]; then
		IFS=, read -r WIDTH HEIGHT <<< "$vs"
	elif [[ "$vs" == *x* ]]; then
		IFS=x read -r WIDTH HEIGHT <<< "$vs"
	fi
fi

if [ "$WIDTH" -eq 0 ] || [ "$HEIGHT" -eq 0 ]; then
	if command -v fbset >/dev/null 2>&1; then
		# fbset -s prints something like: mode "1920x1080" geometry 1920 1080 1920 1080 32
		geom=$(fbset -s | awk '/geometry/ {print $2, $3}') || true
		if [ -n "$geom" ]; then
			WIDTH=$(echo "$geom" | awk '{print $1}')
			HEIGHT=$(echo "$geom" | awk '{print $2}')
		fi
	fi
fi

# Bits per pixel
BPP_BITS=0
if [ -r "$sysdir/bits_per_pixel" ]; then
	BPP_BITS=$(cat "$sysdir/bits_per_pixel")
elif command -v fbset >/dev/null 2>&1; then
	# last number in the geometry line is often bits-per-pixel
	bpp=$(fbset -s | awk '/geometry/ {print $6}') || true
	if [[ "$bpp" =~ ^[0-9]+$ ]]; then
		BPP_BITS=$bpp
	fi
fi

# Defaults if still unknown
if [ -z "$WIDTH" ] || [ -z "$HEIGHT" ] || [ "$WIDTH" -eq 0 ] || [ "$HEIGHT" -eq 0 ]; then
	echo "Could not detect framebuffer resolution; falling back to 1920x1080" >&2
	WIDTH=1920
	HEIGHT=1080
fi

if [ -z "$BPP_BITS" ] || [ "$BPP_BITS" -eq 0 ]; then
	echo "Could not detect bits-per-pixel; falling back to 32bpp" >&2
	BPP_BITS=32
fi

# Convert bits per pixel to bytes per pixel, rounding up where necessary
BPP=$(( (BPP_BITS + 7) / 8 ))

SIZE=$((WIDTH * HEIGHT * BPP))

# Parse hex color (RRGGBB format, # prefix optional)
if [[ ! "$COLOR" =~ ^[0-9A-Fa-f]{6}$ ]]; then
	echo "Error: COLOR must be 6 hex digits (RRGGBB format), got: $COLOR" >&2
	exit 1
fi

# Extract RGB components
R=$(printf "%d" 0x${COLOR:0:2})
G=$(printf "%d" 0x${COLOR:2:2})
B=$(printf "%d" 0x${COLOR:4:2})

echo "Blackout: device=$FBDEV resolution=${WIDTH}x${HEIGHT} bpp=${BPP_BITS} (${BPP} bytes) color=#$COLOR size=${SIZE} bytes"

# Direct framebuffer write - fastest and most reliable method
# Write directly to framebuffer device using dd with a pre-generated buffer

echo "Writing directly to framebuffer..."

# Use Python to generate the full buffer and write it in one go
sudo python3 - "$FBDEV" "$WIDTH" "$HEIGHT" "$R" "$G" "$B" "$BPP" <<'PYGEN'
import sys

fbdev = sys.argv[1]
width = int(sys.argv[2])
height = int(sys.argv[3])
r = int(sys.argv[4])
g = int(sys.argv[5])
b = int(sys.argv[6])
bpp = int(sys.argv[7])

# Construct pixel based on bpp
if bpp == 4:
    pixel = bytes([b, g, r, 255])  # BGRA
elif bpp == 3:
    pixel = bytes([b, g, r])  # BGR
elif bpp == 2:
    val = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
    pixel = val.to_bytes(2, byteorder='little')
else:
    sys.stderr.write(f"Unsupported bpp: {bpp}\n")
    sys.exit(1)

# Generate line and write to framebuffer
line = pixel * width
total_size = width * height * bpp

try:
    with open(fbdev, 'wb') as fb:
        # Write in blocks for efficiency
        block_lines = 100
        block = line * block_lines
        full_blocks = height // block_lines
        remaining_lines = height % block_lines
        
        for _ in range(full_blocks):
            fb.write(block)
        
        if remaining_lines:
            fb.write(line * remaining_lines)
        
        fb.flush()
except Exception as e:
    sys.stderr.write(f"Error writing to framebuffer: {e}\n")
    sys.exit(1)

sys.stderr.write("Done\n")
PYGEN

exit 0