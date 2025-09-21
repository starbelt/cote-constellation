#!/bin/bash
# Complete Spacing Strategy & Link Policy Analysis Pipeline
# Runs simulations for all 4x4 combinations and organizes results

set -e  # Exit on any error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="$SCRIPT_DIR/../../.venv"

echo "============================================================"
echo "COMPLETE 4×4 SPACING & LINK POLICY ANALYSIS PIPELINE"
echo "============================================================"

# Check if virtual environment exists
if [ ! -d "$VENV_PATH" ]; then
    echo "❌ Virtual environment not found at $VENV_PATH"
    echo "Please run the setup script first."
    exit 1
fi

cd "$SCRIPT_DIR"

# Create timestamped output directory
timestamp=$(date +"%Y%m%d_%H%M%S")
OUTPUT_DIR="constellation_analysis_${timestamp}"
mkdir -p "$OUTPUT_DIR"

echo "📁 Creating analysis structure in: $OUTPUT_DIR"

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

for spacing in "${SPACING_STRATEGIES[@]}"; do
    echo ""
    echo "📡 SPACING STRATEGY: $(echo $spacing | tr '[:lower:]' '[:upper:]')"
    echo "------------------------------------------------------------"
    
    for policy in "${POLICIES[@]}"; do
        echo ""
        echo "🎯 Running $spacing with $(echo $policy | tr '[:lower:]' '[:upper:]') policy..."
        
        # Create logs directory for this combination
        logs_dir="logs/${spacing}_${policy}"
        rm -rf "$logs_dir"
        mkdir -p "$logs_dir"
        
        start_time=$(date +%s)
        total_runs=$((total_runs + 1))
        
        # Run simulation
        echo "   Command: ./build/bent_pipe configuration $logs_dir $policy $spacing"
        if ./build/bent_pipe configuration "$logs_dir" "$policy" "$spacing" 2>/dev/null; then
            end_time=$(date +%s)
            duration=$((end_time - start_time))
            file_count=$(ls -1 "$logs_dir"/*.csv 2>/dev/null | wc -l | tr -d ' ')
            
            if [ "$file_count" -gt 0 ]; then
                echo "   ✅ Success! (${duration}s, ${file_count} files)"
                successful_runs=$((successful_runs + 1))
            else
                echo "   ⚠️  No log files generated"
            fi
        else
            end_time=$(date +%s)
            duration=$((end_time - start_time))
            echo "   ❌ Failed! (${duration}s)"
        fi
    done
done

echo ""
echo "📊 SIMULATION SUMMARY"
echo "============================================================"
echo "✅ Successful runs: $successful_runs/$total_runs"

if [ $successful_runs -eq 0 ]; then
    echo "❌ No simulations succeeded! Exiting."
    exit 1
fi

# Step 3: Activate virtual environment for analysis
echo ""
echo "🔬 STEP 3: Running Analysis For Each Spacing Strategy"
echo "============================================================"
echo "Activating virtual environment..."
source "$VENV_PATH/bin/activate"

analysis_success=0
analysis_total=0

for spacing in "${SPACING_STRATEGIES[@]}"; do
    spacing_dir="$OUTPUT_DIR/$spacing"
    
    echo ""
    echo "📊 Analyzing $spacing strategy..."
    echo "------------------------------------------------------------"
    
    # Create temporary logs structure expected by analysis scripts
    temp_logs_dir="logs_temp"
    rm -rf "$temp_logs_dir"
    mkdir -p "$temp_logs_dir"
    
    # Copy logs to expected structure
    policies_found=0
    for policy in "${POLICIES[@]}"; do
        source_logs="logs/${spacing}_${policy}"
        target_logs="$temp_logs_dir/$policy"
        
        if [ -d "$source_logs" ] && [ "$(ls -A "$source_logs" 2>/dev/null)" ]; then
            cp -r "$source_logs" "$target_logs"
            policies_found=$((policies_found + 1))
            echo "   📁 Copied logs for $policy policy"
        else
            echo "   ⚠️  No logs found for $policy policy"
        fi
    done
    
    if [ $policies_found -eq 0 ]; then
        echo "   ❌ No logs found for $spacing strategy - skipping analysis"
        continue
    fi
    
    # Temporarily move current logs and replace with spacing-specific logs
    if [ -d "logs" ]; then
        mv "logs" "logs_backup"
    fi
    mv "$temp_logs_dir" "logs"
    
    # Run analysis
    analysis_total=$((analysis_total + 1))
    start_time=$(date +%s)
    
    if python3 run_combined_analysis.py > /dev/null 2>&1; then
        end_time=$(date +%s)
        duration=$((end_time - start_time))
        echo "   ✅ Analysis completed successfully! (${duration}s)"
        
        # Find the most recent analysis folder and move contents
        latest_analysis=$(ls -td constellation_analysis_* 2>/dev/null | grep -v "$OUTPUT_DIR" | head -1)
        if [ -n "$latest_analysis" ]; then
            # Move PNG files to spacing directory
            for png_file in "$latest_analysis"/*.png; do
                if [ -f "$png_file" ]; then
                    cp "$png_file" "$spacing_dir/"
                    echo "   📊 Copied $(basename "$png_file")"
                fi
            done
            
            # Create log archive for this spacing strategy
            if [ -d "logs" ]; then
                zip_file="$spacing_dir/simulation_logs.zip"
                (cd logs && zip -r "../$zip_file" . > /dev/null 2>&1)
                echo "   📦 Created simulation_logs.zip"
            fi
            
            # Clean up temporary analysis folder
            rm -rf "$latest_analysis"
        fi
        
        analysis_success=$((analysis_success + 1))
    else
        echo "   ❌ Analysis failed!"
    fi
    
    # Restore original logs
    rm -rf "logs"
    if [ -d "logs_backup" ]; then
        mv "logs_backup" "logs"
    fi
done

# Step 4: Generate cross-spacing comparison (if available)
echo ""
echo "📈 STEP 4: Generating Cross-Strategy Comparison"
echo "============================================================"

if [ -f "generate_spacing_comparison.py" ]; then
    echo "Running spacing strategy comparison analysis..."
    if python3 generate_spacing_comparison.py "$OUTPUT_DIR" > /dev/null 2>&1; then
        echo "✅ Spacing comparison charts generated!"
    else
        echo "⚠️  Spacing comparison analysis failed"
    fi
else
    echo "ℹ️  No spacing comparison script found - skipping cross-analysis"
fi

# Final summary
echo ""
echo "============================================================"
echo "COMPLETE 4×4 ANALYSIS PIPELINE FINISHED!"
echo "============================================================"
echo "📁 Output directory: $OUTPUT_DIR"
echo "✅ Simulations: $successful_runs/$total_runs successful"
echo "✅ Analyses: $analysis_success/$analysis_total spacing strategies"
echo ""

# Show final structure
echo "📋 Generated Structure:"
for spacing in "${SPACING_STRATEGIES[@]}"; do
    spacing_dir="$OUTPUT_DIR/$spacing"
    if [ -d "$spacing_dir" ]; then
        file_count=$(ls -1 "$spacing_dir" 2>/dev/null | wc -l | tr -d ' ')
        echo "   📁 $spacing/ ($file_count files)"
        if [ -f "$spacing_dir/buffer_comparison.png" ]; then
            echo "      ✅ Analysis charts generated"
        else
            echo "      ❌ Analysis charts missing"
        fi
    fi
done

echo ""
echo "🎯 Configuration Summary:"
echo "  Buffer Cap: ${BUFFER_MB} MB"
echo "  Image Size: ~29 MB"
echo "  Satellites: 50"
echo "  Total Combinations: $((${#SPACING_STRATEGIES[@]} * ${#POLICIES[@]}))"
echo ""
echo "💡 Complete 4×4 spacing strategy and link policy analysis ready in: $OUTPUT_DIR"
echo "📊 Each spacing strategy contains analysis for all ${#POLICIES[@]} link policies"
echo "📦 Full simulation logs archived per spacing strategy"
