#!/bin/bash
# Generate all 256 CZML files using generate_single_czml.py
# This script calls generate_single_czml.py which handles zip extraction and cleanup automatically

cd "$(dirname "$0")"

TOTAL=720
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
            for policy in fifo sticky random roundrobin mindistance maxdownload; do
                CURRENT=$((CURRENT + 1))
                
                # Check if output file already exists (compressed)
                # Format sat_count: 1->01, 25->25, 50->50, 100->100, 200->200
                # Use %02d for 1-99, keep as-is for 100+
                if [[ $sat_count -lt 100 ]]; then
                    sat_count_formatted=$(printf "%02d" "$sat_count")
                else
                    sat_count_formatted="$sat_count"
                fi
                image_size_padded=$(printf "%05d" "$image_size")
                output_file="cesium_output/${spacing}_${policy}_${sat_count_formatted}sats_${image_size_padded}.czml.gz"
                
                if [[ -f "$output_file" ]]; then
                    echo "[$CURRENT/$TOTAL] $spacing | $policy | ${sat_count} sats | ${image_size} MB"
                    echo "  ⏭️  Skipped (already exists)"
                    continue
                fi
                
                echo "[$CURRENT/$TOTAL] $spacing | $policy | ${sat_count} sats | ${image_size} MB"
                
                # Run the generation and check if output file was created
                python3 generate_single_czml.py "$analysis_dir" "$spacing" "$policy" "$sat_count_formatted" > /dev/null 2>&1
                
                if [[ -f "$output_file" ]]; then
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
