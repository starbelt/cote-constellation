#!/bin/bash
# Run constellation analysis for multiple image sizes (single satellite count)
# Usage: ./run_satellite_comparison.sh [sat_count]
#   sat_count: 1, 50, 100, or 200 (default: 50)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Parse satellite count parameter
SAT_COUNT=${1:-50}  # Default to 50 if not specified

# Validate satellite count
case "$SAT_COUNT" in
    1|50|100|200)
        ;;
    *)
        echo "❌ Error: Invalid satellite count '$SAT_COUNT'"
        echo "   Valid options: 1, 50, 100, 200"
        echo "   Usage: ./run_satellite_comparison.sh [sat_count]"
        exit 1
        ;;
esac

echo "============================================================"
echo "IMAGE SIZE COMPARISON ANALYSIS"
echo "============================================================"

# Define image sizes to compare
IMAGE_SIZES=(028 280 2800 28000)

echo "� Running simulations for image sizes: ${IMAGE_SIZES[*]}"
echo "�️  Satellite count: $SAT_COUNT"
echo ""

for image_size in "${IMAGE_SIZES[@]}"; do
    echo "🚀 Starting analysis for image size $image_size (satellite count $SAT_COUNT)..."
    echo "------------------------------------------------------------"
    
    # Run the main analysis script with the specified satellite count and image size
    if ./run_analysis.sh "$SAT_COUNT" "$image_size"; then
        echo "✅ Completed analysis for image size $image_size"
    else
        echo "❌ Failed analysis for image size $image_size"
        exit 1
    fi
    
    echo ""
done

echo "============================================================"
echo "ALL IMAGE SIZE ANALYSES COMPLETED!"
echo "============================================================"

# Show generated directories
echo "📁 Generated analysis directories:"
ls -1d constellation_analysis_*_*_* 2>/dev/null | sort | sed 's/^/   /'

echo ""
echo "💡 Next steps:"
echo "   • Compare results across different image sizes"
echo "   • Run matrix generation scripts on each directory"
echo "   • Analyze efficiency trends vs image size"