#!/bin/bash
# Generate all 256 CZML files using generate_single_czml.py
# This script calls generate_single_czml.py which handles zip extraction and cleanup automatically

cd "$(dirname "$0")"

TOTAL=256
CURRENT=0
GENERATED=0
FAILED=0

echo "========================================"
echo "Generating all CZML combinations"
echo "Total: $TOTAL"
echo "========================================"
echo ""

for analysis_dir in constellation_analysis_*; do
    # Extract image_size and sat_count from directory name
    # Format: constellation_analysis_YYYYMMDD_HHMMSS_IMAGESIZE_SATCOUNT
    if [[ $analysis_dir =~ _([0-9]+)_([0-9]+)$ ]]; then
        image_size="${BASH_REMATCH[1]}"
        sat_count="${BASH_REMATCH[2]}"
        
        # Find spacing directories
        for spacing_dir in "$analysis_dir"/*/; do
            spacing=$(basename "$spacing_dir")
            
            # Skip if not a valid spacing directory
            if [[ ! -f "$spacing_dir/simulation_logs.zip" ]]; then
                continue
            fi
            
            # Generate for each policy
            for policy in fifo sticky random roundrobin; do
                CURRENT=$((CURRENT + 1))
                
                # Check if output file already exists (compressed)
                # Format sat_count as 2-digit number (01, 50, 100, 200)
                sat_count_padded=$(printf "%02d" "$sat_count")
                image_size_padded=$(printf "%05d" "$image_size")
                output_file="cesium_output/${spacing}_${policy}_${sat_count_padded}sats_${image_size_padded}.czml.gz"
                
                if [[ -f "$output_file" ]]; then
                    echo "[$CURRENT/$TOTAL] $spacing | $policy | ${sat_count} sats | ${image_size} MB"
                    echo "  ⏭️  Skipped (already exists)"
                    continue
                fi
                
                echo "[$CURRENT/$TOTAL] $spacing | $policy | ${sat_count} sats | ${image_size} MB"
                
                if python3 generate_single_czml.py "$analysis_dir" "$spacing" "$policy" "$sat_count" > /dev/null 2>&1; then
                    echo "  ✅ Generated"
                    GENERATED=$((GENERATED + 1))
                else
                    echo "  ❌ Failed"
                    FAILED=$((FAILED + 1))
                fi
            done
        done
    fi
done

echo ""
echo "========================================"
echo "SUMMARY"
echo "========================================"
echo "✅ Generated: $GENERATED"
echo "❌ Failed:    $FAILED"
echo "========================================"
