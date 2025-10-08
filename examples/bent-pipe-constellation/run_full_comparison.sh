#!/bin/bash
# Run constellation analysis for multiple satellite counts and image sizes
# Usage: ./run_full_comparison.sh

#usage: ./run_full_comparison.sh [no args]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================================"
echo "FULL CONSTELLATION COMPARISON ANALYSIS"
echo "============================================================"

# Define satellite counts and image sizes to compare
SAT_COUNTS=(1 50 100 200)
IMAGE_SIZES=(028 280 2800 28000)  # 0.028MB, 0.28MB, 2.8MB, 28MB

echo "🛰️  Satellite counts: ${SAT_COUNTS[*]}"
echo "📷 Image sizes: ${IMAGE_SIZES[*]} (0.028MB, 0.28MB, 2.8MB, 28MB)"
echo "🎯 Total combinations: $((${#SAT_COUNTS[@]} * ${#IMAGE_SIZES[@]}))"
echo ""

combination=0
total_combinations=$((${#SAT_COUNTS[@]} * ${#IMAGE_SIZES[@]}))

for sat_count in "${SAT_COUNTS[@]}"; do
    for image_size in "${IMAGE_SIZES[@]}"; do
        combination=$((combination + 1))
        echo "🚀 Running combination $combination/$total_combinations: $sat_count satellites, ${image_size} image size..."
        echo "------------------------------------------------------------"
        
        # Run the main analysis script with the specified parameters
        if ./run_analysis.sh "$sat_count" "$image_size"; then
            echo "✅ Completed: $sat_count satellites, ${image_size} image size"
        else
            echo "❌ Failed: $sat_count satellites, ${image_size} image size"
            exit 1
        fi
        
        echo ""
    done
done

echo "============================================================"
echo "ALL COMBINATIONS COMPLETED!"
echo "============================================================"

# Show generated directories
echo "📁 Generated analysis directories:"
ls -1d constellation_analysis_*_*_* 2>/dev/null | sort | sed 's/^/   /'

echo ""
echo "💡 Next steps:"
echo "   • Compare efficiency vs satellite count for each image size"
echo "   • Compare efficiency vs image size for each satellite count"
echo "   • Run matrix generation scripts on each directory"
echo "   • Analyze scaling trends across all parameters"