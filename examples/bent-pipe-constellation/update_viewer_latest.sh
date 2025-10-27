#!/bin/bash
# Auto-update constellation_viewer.html with latest CZML files

cd "$(dirname "$0")/cesium_output"

echo "=== Updating constellation_viewer.html with latest CZML files ==="

# Find latest files for each configuration
LATEST_50=$(ls -t close-orbit-spaced_sticky_50sats_*.czml 2>/dev/null | head -1)
LATEST_100=$(ls -t close-orbit-spaced_sticky_100sats_*.czml 2>/dev/null | head -1)
LATEST_200=$(ls -t close-orbit-spaced_sticky_200sats_*.czml 2>/dev/null | head -1)

if [ -z "$LATEST_50" ] && [ -z "$LATEST_100" ] && [ -z "$LATEST_200" ]; then
    echo "❌ Error: Could not find any latest CZML files"
    exit 1
fi

# Update what we found
[ -n "$LATEST_50" ] && echo "   50 sats: $LATEST_50" && sed -i '' "s/\"close-orbit-spaced_sticky_50\": \"close-orbit-spaced_sticky_50sats_[0-9]*mb\.czml\"/\"close-orbit-spaced_sticky_50\": \"$LATEST_50\"/" constellation_viewer.html

[ -n "$LATEST_100" ] && echo "  100 sats: $LATEST_100" && sed -i '' "s/\"close-orbit-spaced_sticky_100\": \"close-orbit-spaced_sticky_100sats_[0-9]*mb\.czml\"/\"close-orbit-spaced_sticky_100\": \"$LATEST_100\"/" constellation_viewer.html

[ -n "$LATEST_200" ] && echo "  200 sats: $LATEST_200" && sed -i '' "s/\"close-orbit-spaced_sticky_200\": \"close-orbit-spaced_sticky_200sats_[0-9]*mb\.czml\"/\"close-orbit-spaced_sticky_200\": \"$LATEST_200\"/" constellation_viewer.html

echo "✅ Updated constellation_viewer.html"
