#!/bin/bash
# Complete Spacing Strategy & Link Policy Simulation Pipeline
# Runs simulations for all 4x4 combinations and organizes results

set -e  # Exit on any error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "============================================================"
echo "COMPLETE 4×4 SPACING & LINK POLICY SIMULATION PIPELINE"
echo "============================================================"

cd "$SCRIPT_DIR"

# Create timestamped output directory
timestamp=$(date +"%Y%m%d_%H%M%S")
OUTPUT_DIR="constellation_analysis_${timestamp}"
mkdir -p "$OUTPUT_DIR"

echo "📁 Creating simulation structure in: $OUTPUT_DIR"

# Read current buffer configuration
BUFFER_MB=$(grep -v "^bits-per-sense" configuration/sensor.dat | cut -d',' -f5)

# Define spacing strategies and link policies
SPACING_STRATEGIES=("close-spaced" "close-orbit-spaced" "frame-spaced" "orbit-spaced")
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
    SAT_COUNT="${CONSTELLATION_PARAMS[0]}"
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
echo "  Satellites: 50"
echo "  Total Combinations: $((${#SPACING_STRATEGIES[@]} * ${#POLICIES[@]}))"
echo ""
echo "💡 4×4 simulation data ready in: $OUTPUT_DIR"
echo "� Each spacing strategy contains simulation_logs.zip with all policy data"
echo "� Run individual analysis scripts as needed against the simulation data"
