#!/bin/bash
# Complete Spacing Strategy & Link Policy Simulation Pipeline
# Runs simulations for all 4x4 combinations and organizes results
# Usage: ./run_analysis.sh [satellite_count] [image_size]
#   satellite_count: 1, 50, 100, or 200 (default: 50)
#   image_size: 028, 280, 2800, or 28000 (default: 28000, represents 0.028, 0.28, 2.8, 28 MB)

set -e  # Exit on any error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Parse parameters
SAT_COUNT=${1:-50}        # Default to 50 if not specified
IMAGE_SIZE_CODE=${2:-28000}  # Default to 28000 (28 MB) if not specified

# Validate satellite count
case "$SAT_COUNT" in
    1|50|100|200)
        ;;
    *)
        echo "❌ Error: Invalid satellite count '$SAT_COUNT'"
        echo "   Valid options: 1, 50, 100, 200"
        echo "   Usage: ./run_analysis.sh [satellite_count] [image_size]"
        exit 1
        ;;
esac

# Validate image size code
case "$IMAGE_SIZE_CODE" in
    028|280|2800|28000)
        ;;
    *)
        echo "❌ Error: Invalid image size code '$IMAGE_SIZE_CODE'"
        echo "   Valid options: 028 (0.028MB), 280 (0.28MB), 2800 (2.8MB), 28000 (28MB)"
        echo "   Usage: ./run_analysis.sh [satellite_count] [image_size]"
        exit 1
        ;;
esac

# Format satellite count for file names (2 digits with leading zeros)
SAT_COUNT_FORMATTED=$(printf "%02d" "$SAT_COUNT")

echo "============================================================"
echo "COMPLETE 4×4 SPACING & LINK POLICY SIMULATION PIPELINE"
echo "============================================================"

cd "$SCRIPT_DIR"

# Copy the appropriate sensor file for the specified image size
SENSOR_SOURCE="data/sensor_${IMAGE_SIZE_CODE}.dat"
if [ -f "$SENSOR_SOURCE" ]; then
    echo "   📷 Using sensor file: $SENSOR_SOURCE"
    cp "$SENSOR_SOURCE" "configuration/sensor.dat"
else
    echo "   ❌ Error: Sensor file not found: $SENSOR_SOURCE"
    echo "   Available files:"
    ls -1 data/sensor_*.dat | sed 's/^/     /'
    exit 1
fi

# Read sensor configuration to get image size
SENSOR_CONFIG="configuration/sensor.dat"
if [ -f "$SENSOR_CONFIG" ]; then
    SENSOR_LINE=$(grep -v "^bits-per-sense" "$SENSOR_CONFIG" | head -1)
    IFS=',' read -ra SENSOR_PARAMS <<< "$SENSOR_LINE"
    BITS_PER_SENSE="${SENSOR_PARAMS[0]}"
    
    # Calculate image size and format as 5-digit number
    # Convert bits to MB, then to integer representation for folder naming
    IMAGE_SIZE_MB=$(echo "scale=3; $BITS_PER_SENSE / 8 / 1024 / 1024" | bc -l)
    # Convert to integer format for folder naming (e.g., 0.028 -> 00028, 28.99 -> 28000)
    IMAGE_SIZE_INT=$(echo "$IMAGE_SIZE_MB * 1000" | bc -l | cut -d'.' -f1)
    IMAGE_SIZE_FORMATTED=$(printf "%05d" "$IMAGE_SIZE_INT")
else
    echo "❌ Error: sensor.dat not found"
    exit 1
fi

# Create timestamped output directory with image size and satellite count
timestamp=$(date +"%Y%m%d_%H%M%S")
OUTPUT_DIR="constellation_analysis_${timestamp}_${IMAGE_SIZE_FORMATTED}_${SAT_COUNT_FORMATTED}"
mkdir -p "$OUTPUT_DIR"

echo "📁 Creating simulation structure in: $OUTPUT_DIR"
echo "🛰️  Satellite count: $SAT_COUNT"
echo "📷 Image size: ${IMAGE_SIZE_MB} MB (code: ${IMAGE_SIZE_CODE})"

# Read current buffer configuration
BUFFER_MB=$(grep -v "^bits-per-sense" configuration/sensor.dat | cut -d',' -f5)

# Define spacing strategies and link policies
# If SINGLE_STRATEGY environment variable is set, only run that strategy
if [ -n "$SINGLE_STRATEGY" ]; then
    # Validate the single strategy
    case "$SINGLE_STRATEGY" in
        close-spaced|orbit-spaced|frame-spaced|close-orbit-spaced)
            SPACING_STRATEGIES=("$SINGLE_STRATEGY")
            echo "🎯 Single strategy mode: $SINGLE_STRATEGY"
            ;;
        *)
            echo "❌ Error: Invalid SINGLE_STRATEGY='$SINGLE_STRATEGY'"
            echo "   Valid options: close-spaced, orbit-spaced, frame-spaced, close-orbit-spaced"
            exit 1
            ;;
    esac
else
    SPACING_STRATEGIES=("close-spaced" "close-orbit-spaced" "frame-spaced" "orbit-spaced")
fi

POLICIES=("sticky" "fifo" "roundrobin" "random")

echo "📋 Configuration:"
echo "  Buffer Cap: ${BUFFER_MB} MB"
echo "  Spacing Strategies: ${SPACING_STRATEGIES[*]}"
echo "  Link Policies: ${POLICIES[*]}"
echo "🎯 Total combinations: ${#SPACING_STRATEGIES[@]} × ${#POLICIES[@]} = $((${#SPACING_STRATEGIES[@]} * ${#POLICIES[@]}))"
echo ""

# Create directory structure
for spacing in "${SPACING_STRATEGIES[@]}"; do
    mkdir -p "$OUTPUT_DIR/$spacing"
done

# Step 1: Build the simulation
echo "🔨 STEP 1: Building Simulation"
echo "============================================================"
cd build && make clean && make && cd ..

# Step 2: Run all simulations
echo ""
echo "🚀 STEP 2: Running All Simulations (4×4 = 16 combinations)"
echo "============================================================"

total_runs=0
successful_runs=0

# Clean up any existing logs first
echo "🧹 Cleaning up existing logs..."
rm -rf logs/*

for spacing in "${SPACING_STRATEGIES[@]}"; do
    echo ""
    echo "📡 SPACING STRATEGY: $(echo $spacing | tr '[:lower:]' '[:upper:]')"
    echo "------------------------------------------------------------"
    
    # Copy the appropriate constellation file for this satellite count and spacing strategy
    # Map spacing strategy names to constellation file prefixes
    case "$spacing" in
        "close-spaced")
            SPACING_FILE_PREFIX="close"
            ;;
        "close-orbit-spaced")
            SPACING_FILE_PREFIX="close_orbit"
            ;;
        "frame-spaced")
            SPACING_FILE_PREFIX="frame"
            ;;
        "orbit-spaced")
            SPACING_FILE_PREFIX="orbit"
            ;;
        *)
            echo "   ❌ Error: Unknown spacing strategy: $spacing"
            exit 1
            ;;
    esac
    
    CONSTELLATION_SOURCE="data/constellation_${SPACING_FILE_PREFIX}_${SAT_COUNT_FORMATTED}.dat"
    
    if [ -f "$CONSTELLATION_SOURCE" ]; then
        echo "   🛰️  Using constellation file: $CONSTELLATION_SOURCE"
        cp "$CONSTELLATION_SOURCE" "configuration/constellation.dat"
    else
        echo "   ❌ Error: Constellation file not found: $CONSTELLATION_SOURCE"
        echo "   Available files:"
        ls -1 data/constellation_*.dat | sed 's/^/     /'
        exit 1
    fi
    
    # Create temporary directory for this spacing strategy's logs
    temp_spacing_dir="temp_${spacing}"
    rm -rf "$temp_spacing_dir"
    mkdir -p "$temp_spacing_dir"
    
    # Copy configuration files to temp directory so they're included in simulation_logs.zip
    mkdir -p "$temp_spacing_dir/configuration"
    cp configuration/*.dat "$temp_spacing_dir/configuration/" 2>/dev/null || true
    
    for policy in "${POLICIES[@]}"; do
        echo ""
        echo "🎯 Running $spacing with $(echo $policy | tr '[:lower:]' '[:upper:]') policy..."
        
        # Clean simulation logs directory for each run
        rm -rf logs/*
        mkdir -p logs
        
        start_time=$(date +%s)
        total_runs=$((total_runs + 1))
        
        # Run simulation directly to logs directory
        echo "   Command: ./build/bent_pipe configuration logs $policy $spacing"
        if ./build/bent_pipe configuration "logs" "$policy" "$spacing" 2>/dev/null; then
            end_time=$(date +%s)
            duration=$((end_time - start_time))
            file_count=$(ls -1 logs/*.csv 2>/dev/null | wc -l | tr -d ' ')
            
            if [ "$file_count" -gt 0 ]; then
                echo "   ✅ Success! (${duration}s, ${file_count} files)"
                successful_runs=$((successful_runs + 1))
                
                # Create policy subdirectory in temp area and copy logs
                policy_dir="$temp_spacing_dir/$policy"
                mkdir -p "$policy_dir"
                cp logs/*.csv "$policy_dir/" 2>/dev/null || true
                echo "   📦 Staged logs for $policy policy"
            else
                echo "   ⚠️  No log files generated"
            fi
        else
            end_time=$(date +%s)
            duration=$((end_time - start_time))
            echo "   ❌ Failed! (${duration}s)"
        fi
    done
    
    # Create simulation_logs.zip for this spacing strategy
    if [ -d "$temp_spacing_dir" ] && [ "$(ls -A "$temp_spacing_dir" 2>/dev/null)" ]; then
        echo ""
        echo "📦 Creating simulation_logs.zip for $spacing strategy..."
        (cd "$temp_spacing_dir" && zip -r "../$OUTPUT_DIR/$spacing/simulation_logs.zip" . > /dev/null 2>&1)
        
        # Count policies with data
        policy_count=$(ls -1 "$temp_spacing_dir" 2>/dev/null | wc -l | tr -d ' ')
        echo "   ✅ Archived $policy_count policies to simulation_logs.zip"
        
        # Clean up temp directory
        rm -rf "$temp_spacing_dir"
    fi
done

echo ""
echo "📊 SIMULATION SUMMARY"
echo "============================================================"
echo "✅ Successful runs: $successful_runs/$total_runs"

if [ $successful_runs -eq 0 ]; then
    echo "❌ No simulations succeeded! Exiting."
    exit 1
fi

# Clean up working logs directory
echo ""
echo "🧹 Cleaning up working logs..."
rm -rf logs

# Clean up working logs directory
echo ""
echo "🧹 Cleaning up working logs..."
rm -rf logs

# Generate simple simulation summary
echo ""
echo "📄 Generating simulation summary..."
SUMMARY_FILE="$OUTPUT_DIR/simulation_summary.txt"

# Read configuration details
SENSOR_CONFIG="configuration/sensor.dat"
CONSTELLATION_CONFIG="configuration/constellation.dat"

# Extract sensor parameters
if [ -f "$SENSOR_CONFIG" ]; then
    SENSOR_LINE=$(grep -v "^bits-per-sense" "$SENSOR_CONFIG" | head -1)
    IFS=',' read -ra SENSOR_PARAMS <<< "$SENSOR_LINE"
    BITS_PER_SENSE="${SENSOR_PARAMS[0]}"
    PIXEL_COUNT="${SENSOR_PARAMS[1]}"
    PIXEL_SIZE_M="${SENSOR_PARAMS[2]}"
    FOCAL_LENGTH_M="${SENSOR_PARAMS[3]}"
    BUFFER_CAP="${SENSOR_PARAMS[4]}"
    
    # Calculate image size from bits-per-sense
    IMAGE_SIZE_MB=$(echo "scale=3; $BITS_PER_SENSE / 8 / 1024 / 1024" | bc -l)
fi

# Extract constellation parameters
if [ -f "$CONSTELLATION_CONFIG" ]; then
    CONSTELLATION_LINE=$(grep -v "^count" "$CONSTELLATION_CONFIG" | head -1)
    IFS=',' read -ra CONSTELLATION_PARAMS <<< "$CONSTELLATION_LINE"
    CONFIG_SAT_COUNT="${CONSTELLATION_PARAMS[0]}"
    
    # Verify that the constellation file matches our expected satellite count
    if [ "$CONFIG_SAT_COUNT" != "$(printf "%05d" "$SAT_COUNT")" ]; then
        echo "⚠️  Warning: Constellation file satellite count ($CONFIG_SAT_COUNT) doesn't match expected ($SAT_COUNT)"
    fi
else
    CONFIG_SAT_COUNT="$(printf "%05d" "$SAT_COUNT")"
fi

# Read additional configuration for comprehensive stats
NUM_STEPS_CONFIG="configuration/num-steps.dat"
TIME_STEP_CONFIG="configuration/time-step.dat"

# Extract number of simulation steps
if [ -f "$NUM_STEPS_CONFIG" ]; then
    NUM_STEPS_LINE=$(grep -v "^steps" "$NUM_STEPS_CONFIG" | head -1)
    NUM_STEPS="$NUM_STEPS_LINE"
fi

# Extract time step (assuming 1 second per step as default)
TIME_STEP_SECONDS=1
if [ -f "$TIME_STEP_CONFIG" ]; then
    TIME_STEP_LINE=$(grep -v "^hour" "$TIME_STEP_CONFIG" | head -1)
    IFS=',' read -ra TIME_PARAMS <<< "$TIME_STEP_LINE"
    # Convert to seconds: hour*3600 + minute*60 + second + nanosecond/1e9
    HOURS="${TIME_PARAMS[0]}"
    MINUTES="${TIME_PARAMS[1]}"
    SECONDS="${TIME_PARAMS[2]}"
    NANOSECONDS="${TIME_PARAMS[3]}"
    TIME_STEP_SECONDS=$(echo "scale=3; $HOURS * 3600 + $MINUTES * 60 + $SECONDS + $NANOSECONDS / 1000000000" | bc -l)
fi

# Calculate total simulation duration
if [ -n "$NUM_STEPS" ] && [ -n "$TIME_STEP_SECONDS" ]; then
    TOTAL_DURATION_SEC=$(echo "scale=1; $NUM_STEPS * $TIME_STEP_SECONDS" | bc -l)
    TOTAL_DURATION_HOURS=$(echo "scale=2; $TOTAL_DURATION_SEC / 3600" | bc -l)
fi

# Create simple summary
cat > "$SUMMARY_FILE" << EOF
Simulation Configuration Statistics
===================================

Image Size: ${IMAGE_SIZE_MB} MB
Max Buffer: ${BUFFER_CAP} MB  
Satellite Count: ${SAT_COUNT}
Total Steps: ${NUM_STEPS}
Time Step: ${TIME_STEP_SECONDS}s
Total Duration: ${TOTAL_DURATION_HOURS}h (${TOTAL_DURATION_SEC}s)
Strategies: 4 (close-spaced, close-orbit-spaced, frame-spaced, orbit-spaced)
Policies: 4 (sticky, fifo, roundrobin, random)
Total Combinations: 16
EOF

echo "   ✅ Created simulation_summary.txt"

# Final summary
echo ""
echo "============================================================"
echo "COMPLETE 4×4 SIMULATION PIPELINE FINISHED!"
echo "============================================================"
echo "📁 Output directory: $OUTPUT_DIR"
echo "✅ Simulations: $successful_runs/$total_runs successful"
echo ""

# Show final structure
echo "📋 Generated Structure:"
for spacing in "${SPACING_STRATEGIES[@]}"; do
    spacing_dir="$OUTPUT_DIR/$spacing"
    if [ -d "$spacing_dir" ]; then
        zip_exists="❌"
        if [ -f "$spacing_dir/simulation_logs.zip" ]; then
            zip_exists="✅"
            zip_size=$(ls -lh "$spacing_dir/simulation_logs.zip" 2>/dev/null | awk '{print $5}')
            echo "   📁 $spacing/ → simulation_logs.zip ($zip_size)"
        else
            echo "   📁 $spacing/ → simulation_logs.zip (missing)"
        fi
    fi
done

echo ""
echo "🎯 Configuration Summary:"
echo "  Buffer Cap: ${BUFFER_MB} MB"
echo "  Satellites: $SAT_COUNT"
echo "  Total Combinations: $((${#SPACING_STRATEGIES[@]} * ${#POLICIES[@]}))"
echo ""
echo "💡 4×4 simulation data ready in: $OUTPUT_DIR"
echo "� Each spacing strategy contains simulation_logs.zip with all policy data"
echo "� Run individual analysis scripts as needed against the simulation data"
