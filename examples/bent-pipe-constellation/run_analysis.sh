#!/bin/bash
# Flexible Constellation Simulation Pipeline
# Run any combination of spacing strategies, link policies, satellite counts, and image sizes
# 
# Usage: ./run_analysis.sh [policies] [sat_counts] [spacings] [image_sizes]
#   All parameters are optional and accept comma-separated lists
#
# Examples:
#   ./run_analysis.sh                                    # Run everything (256 simulations!)
#   ./run_analysis.sh fifo                               # Run FIFO for all configs
#   ./run_analysis.sh "fifo,roundrobin"                  # Run FIFO and roundrobin for all configs
#   ./run_analysis.sh fifo 50                            # Run FIFO with 50 sats
#   ./run_analysis.sh fifo "50,100"                      # Run FIFO with 50 and 100 sats
#   ./run_analysis.sh "fifo,roundrobin" "50,100"         # Run 2 policies × 2 sat counts
#   ./run_analysis.sh fifo 50 close-spaced               # Run FIFO, 50 sats, close-spaced
#   ./run_analysis.sh fifo "50,100" "close-spaced,orbit-spaced"  # 2×2 combo
#   ./run_analysis.sh "" 100                             # All policies with 100 sats
#   ./run_analysis.sh "" "50,100" orbit-spaced           # All policies, 2 sat counts, 1 strategy
#
# Valid values (use comma-separated for multiple):
#   policies:    sticky, fifo, roundrobin, random (or "" for all)
#   sat_counts:  1, 50, 100, 200 (or "" for all)
#   spacings:    close-spaced, orbit-spaced, frame-spaced, close-orbit-spaced (or "" for all)
#   image_sizes: 028, 280, 2800, 28000 (or "" for all)

set -e  # Exit on any error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Parse parameters (all optional, comma-separated)
PARAM_POLICY=${1:-""}
PARAM_SAT_COUNT=${2:-""}
PARAM_SPACING=${3:-""}
PARAM_IMAGE_SIZE=${4:-""}

# Define all possible values
ALL_POLICIES=("sticky" "fifo" "roundrobin" "random")
ALL_SAT_COUNTS=(1 50 100 200)
ALL_SPACING_STRATEGIES=("close-spaced" "close-orbit-spaced" "frame-spaced" "orbit-spaced")
ALL_IMAGE_SIZES=(028 280 2800 28000)

# Function to parse comma-separated list into array
parse_list() {
    local input="$1"
    local output_array_name="$2"
    
    if [ -z "$input" ]; then
        return 1  # Empty, use defaults
    fi
    
    # Split by comma into array
    IFS=',' read -ra items <<< "$input"
    
    # Remove spaces and store in output array
    local cleaned=()
    for item in "${items[@]}"; do
        cleaned+=("$(echo "$item" | xargs)")  # xargs trims whitespace
    done
    
    eval "$output_array_name=(\"\${cleaned[@]}\")"
    return 0
}

# Determine which policies to run
if parse_list "$PARAM_POLICY" "POLICY_LIST"; then
    POLICIES=()
    for policy in "${POLICY_LIST[@]}"; do
        case "$policy" in
            sticky|fifo|roundrobin|random)
                POLICIES+=("$policy")
                ;;
            *)
                echo "❌ Error: Invalid policy '$policy'"
                echo "   Valid options: sticky, fifo, roundrobin, random"
                echo "   Use comma-separated list: fifo,roundrobin"
                exit 1
                ;;
        esac
    done
else
    POLICIES=("${ALL_POLICIES[@]}")
fi

# Determine which satellite counts to run
if parse_list "$PARAM_SAT_COUNT" "SAT_COUNT_LIST"; then
    SAT_COUNTS=()
    for count in "${SAT_COUNT_LIST[@]}"; do
        case "$count" in
            1|50|100|200)
                SAT_COUNTS+=("$count")
                ;;
            *)
                echo "❌ Error: Invalid satellite count '$count'"
                echo "   Valid options: 1, 50, 100, 200"
                echo "   Use comma-separated list: 50,100"
                exit 1
                ;;
        esac
    done
else
    SAT_COUNTS=("${ALL_SAT_COUNTS[@]}")
fi

# Determine which spacing strategies to run
if parse_list "$PARAM_SPACING" "SPACING_LIST"; then
    SPACING_STRATEGIES=()
    for spacing in "${SPACING_LIST[@]}"; do
        case "$spacing" in
            close-spaced|orbit-spaced|frame-spaced|close-orbit-spaced)
                SPACING_STRATEGIES+=("$spacing")
                ;;
            *)
                echo "❌ Error: Invalid spacing strategy '$spacing'"
                echo "   Valid options: close-spaced, orbit-spaced, frame-spaced, close-orbit-spaced"
                echo "   Use comma-separated list: close-spaced,orbit-spaced"
                exit 1
                ;;
        esac
    done
else
    SPACING_STRATEGIES=("${ALL_SPACING_STRATEGIES[@]}")
fi

# Determine which image sizes to run
if parse_list "$PARAM_IMAGE_SIZE" "IMAGE_SIZE_LIST"; then
    IMAGE_SIZES=()
    for size in "${IMAGE_SIZE_LIST[@]}"; do
        case "$size" in
            028|280|2800|28000)
                IMAGE_SIZES+=("$size")
                ;;
            *)
                echo "❌ Error: Invalid image size '$size'"
                echo "   Valid options: 028, 280, 2800, 28000"
                echo "   Use comma-separated list: 028,28000"
                exit 1
                ;;
        esac
    done
else
    IMAGE_SIZES=("${ALL_IMAGE_SIZES[@]}")
fi


# Calculate total number of simulations
TOTAL_SIMS=$((${#POLICIES[@]} * ${#SAT_COUNTS[@]} * ${#SPACING_STRATEGIES[@]} * ${#IMAGE_SIZES[@]}))

echo "============================================================"
echo "FLEXIBLE CONSTELLATION SIMULATION PIPELINE"
echo "============================================================"
echo ""
echo "📋 Configuration:"
echo "   Policies: ${POLICIES[*]}"
echo "   Satellite Counts: ${SAT_COUNTS[*]}"
echo "   Spacing Strategies: ${SPACING_STRATEGIES[*]}"
echo "   Image Sizes: ${IMAGE_SIZES[*]}"
echo ""
echo "🎯 Total simulations: ${#POLICIES[@]} policies × ${#SAT_COUNTS[@]} sat counts × ${#SPACING_STRATEGIES[@]} strategies × ${#IMAGE_SIZES[@]} image sizes = $TOTAL_SIMS"
echo ""

if [ $TOTAL_SIMS -gt 50 ]; then
    echo "⚠️  Warning: Running $TOTAL_SIMS simulations will take significant time!"
    echo "   Estimated time: $(($TOTAL_SIMS * 3 / 60)) - $(($TOTAL_SIMS * 5 / 60)) hours"
    echo ""
    read -p "   Continue? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Cancelled."
        exit 0
    fi
fi

cd "$SCRIPT_DIR"

# Step 1: Build the simulation once
echo "🔨 STEP 1: Building Simulation"
echo "============================================================"
cd build && make clean && make && cd ..

# Step 2: Run all simulations
echo ""
echo "🚀 STEP 2: Running All Simulations"
echo "============================================================"

SIMULATION_NUM=0
SUCCESSFUL_RUNS=0

# Outer loops: image size and satellite count (these determine the output directory)
for IMAGE_SIZE_CODE in "${IMAGE_SIZES[@]}"; do
    for SAT_COUNT in "${SAT_COUNTS[@]}"; do
        
        # Format satellite count for file names
        SAT_COUNT_FORMATTED=$(printf "%02d" "$SAT_COUNT")
        
        # Copy the appropriate sensor file for the specified image size
        SENSOR_SOURCE="data/sensor_${IMAGE_SIZE_CODE}.dat"
        if [ -f "$SENSOR_SOURCE" ]; then
            cp "$SENSOR_SOURCE" "configuration/sensor.dat"
        else
            echo "❌ Error: Sensor file not found: $SENSOR_SOURCE"
            exit 1
        fi
        
        # Read sensor configuration to get image size
        SENSOR_CONFIG="configuration/sensor.dat"
        SENSOR_LINE=$(grep -v "^bits-per-sense" "$SENSOR_CONFIG" | head -1)
        IFS=',' read -ra SENSOR_PARAMS <<< "$SENSOR_LINE"
        BITS_PER_SENSE="${SENSOR_PARAMS[0]}"
        
        # Calculate image size and format as 5-digit number
        IMAGE_SIZE_MB=$(echo "scale=3; $BITS_PER_SENSE / 8 / 1024 / 1024" | bc -l)
        IMAGE_SIZE_INT=$(echo "$IMAGE_SIZE_MB * 1000" | bc -l | cut -d'.' -f1)
        IMAGE_SIZE_FORMATTED=$(printf "%05d" "$IMAGE_SIZE_INT")
        
        # Create timestamped output directory with image size and satellite count
        timestamp=$(date +"%Y%m%d_%H%M%S")
        OUTPUT_DIR="constellation_analysis_${timestamp}_${IMAGE_SIZE_FORMATTED}_${SAT_COUNT_FORMATTED}"
        mkdir -p "$OUTPUT_DIR"
        
        echo ""
        echo "════════════════════════════════════════════════════════"
        echo "📁 Output Directory: $OUTPUT_DIR"
        echo "🛰️  Satellite Count: $SAT_COUNT"
        echo "📷 Image Size: ${IMAGE_SIZE_MB} MB (code: ${IMAGE_SIZE_CODE})"
        echo "════════════════════════════════════════════════════════"
        
        # Create directory structure for strategies
        for spacing in "${SPACING_STRATEGIES[@]}"; do
            mkdir -p "$OUTPUT_DIR/$spacing"
        done
        
        # Inner loops: spacing strategy and policy
        for spacing in "${SPACING_STRATEGIES[@]}"; do
            echo ""
            echo "📡 SPACING STRATEGY: $(echo $spacing | tr '[:lower:]' '[:upper:]')"
            echo "------------------------------------------------------------"
            
            # Copy the appropriate constellation file
            case "$spacing" in
                "close-spaced")      SPACING_FILE_PREFIX="close" ;;
                "close-orbit-spaced") SPACING_FILE_PREFIX="close_orbit" ;;
                "frame-spaced")      SPACING_FILE_PREFIX="frame" ;;
                "orbit-spaced")      SPACING_FILE_PREFIX="orbit" ;;
            esac
            
            CONSTELLATION_SOURCE="data/constellation_${SPACING_FILE_PREFIX}_${SAT_COUNT_FORMATTED}.dat"
            
            if [ -f "$CONSTELLATION_SOURCE" ]; then
                cp "$CONSTELLATION_SOURCE" "configuration/constellation.dat"
            else
                echo "   ❌ Error: Constellation file not found: $CONSTELLATION_SOURCE"
                exit 1
            fi
            
            # Create temporary directory for this spacing strategy's logs
            temp_spacing_dir="temp_${spacing}"
            rm -rf "$temp_spacing_dir"
            mkdir -p "$temp_spacing_dir"
            
            # Copy configuration files
            mkdir -p "$temp_spacing_dir/configuration"
            cp configuration/*.dat "$temp_spacing_dir/configuration/" 2>/dev/null || true
            
            for policy in "${POLICIES[@]}"; do
                ((SIMULATION_NUM++))
                
                echo ""
                echo "[$SIMULATION_NUM/$TOTAL_SIMS] 🎯 Running $spacing with $(echo $policy | tr '[:lower:]' '[:upper:]') policy..."
                
                # Clean simulation logs directory
                rm -rf logs/*
                mkdir -p logs
                
                start_time=$(date +%s)
                
                # Run simulation
                if ./build/bent_pipe configuration "logs" "$policy" "$spacing" 2>/dev/null; then
                    end_time=$(date +%s)
                    duration=$((end_time - start_time))
                    file_count=$(ls -1 logs/*.csv 2>/dev/null | wc -l | tr -d ' ')
                    
                    if [ "$file_count" -gt 0 ]; then
                        echo "   ✅ Success! (${duration}s, ${file_count} files)"
                        ((SUCCESSFUL_RUNS++))
                        
                        # Create policy subdirectory and copy logs
                        policy_dir="$temp_spacing_dir/$policy"
                        mkdir -p "$policy_dir"
                        cp logs/*.csv "$policy_dir/" 2>/dev/null || true
                    else
                        echo "   ⚠️  No log files generated"
                    fi
                else
                    echo "   ❌ Simulation failed"
                fi
            done
            
            # After all policies for this spacing strategy, create zip file
            if [ -d "$temp_spacing_dir" ]; then
                echo ""
                echo "📦 Packaging logs for $spacing..."
                cd "$temp_spacing_dir"
                zip -r "../${OUTPUT_DIR}/${spacing}/simulation_logs.zip" . > /dev/null 2>&1
                cd "$SCRIPT_DIR"
                rm -rf "$temp_spacing_dir"
                echo "   ✅ Created ${OUTPUT_DIR}/${spacing}/simulation_logs.zip"
            fi
        done
        
        echo ""
        echo "✅ Completed all simulations for $OUTPUT_DIR"
        echo ""
    done
done

# Final summary
echo ""
echo "============================================================"
echo "FLEXIBLE SIMULATION PIPELINE COMPLETE!"
echo "============================================================"
echo "✅ Successful simulations: $SUCCESSFUL_RUNS/$TOTAL_SIMS"
echo ""
echo "📊 Summary:"
echo "   Policies run: ${POLICIES[*]}"
echo "   Satellite counts: ${SAT_COUNTS[*]}"
echo "   Spacing strategies: ${SPACING_STRATEGIES[*]}"
echo "   Image sizes: ${IMAGE_SIZES[*]}"
echo ""

# Show generated directories
echo "📁 Generated directories:"
ls -1dt constellation_analysis_* 2>/dev/null | head -10 | while read dir; do
    if [ -d "$dir" ]; then
        # Extract info from directory name
        dir_name=$(basename "$dir")
        echo "   ✅ $dir_name"
        
        # Show what's inside
        for spacing in "${SPACING_STRATEGIES[@]}"; do
            if [ -f "$dir/$spacing/simulation_logs.zip" ]; then
                zip_size=$(ls -lh "$dir/$spacing/simulation_logs.zip" 2>/dev/null | awk '{print $5}')
                echo "      └─ $spacing/simulation_logs.zip ($zip_size)"
            fi
        done
    fi
done

echo ""
echo "💡 Next steps:"
echo "   • Run analysis scripts on generated data"
echo "   • Compare performance across configurations"
echo "   • Generate visualizations with plot scripts"

