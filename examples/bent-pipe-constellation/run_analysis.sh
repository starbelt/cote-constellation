#!/bin/bash
# Complete Simulation and Analysis Pipeline
# This script runs all schedulinecho ""
echo "============================================================"
echo "COMPLETE PIPELINE FINISHED"
echo "============================================================"

# Summary of results
echo "📊 RESULTS SUMMARY:"
echo "  🔧 Fresh simulations run for all 4 policies"
echo "  📊 Buffer Analysis: constellation_analysis_*/buffer_comparison.png"
echo "  📊 Data Loss Analysis: constellation_analysis_*/loss_comparison.png (if applicable)"
echo "  📊 Distribution Analysis: constellation_analysis_*/satellite_distribution_bars.png"
echo "  📦 Complete Logs: constellation_analysis_*/simulation_logs.zip"
echo ""
echo "🎯 Configuration used:"
echo "  Buffer Cap: ${BUFFER_MB} MB"
echo "  Image Size: ~29 MB"
echo "  Satellites: 50"
echo ""
echo "💡 To modify buffer cap, edit configuration/sensor.dat (max-buffer-mb)"
echo "💡 All charts show comprehensive multi-satellite constellation analysis"
echo "💡 Check the latest constellation_analysis_* folder for all outputs"nerates both buffer and loss analyses

set -e  # Exit on any error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="$SCRIPT_DIR/../../.venv"

echo "============================================================"
echo "COMPLETE SIMULATION AND ANALYSIS PIPELINE"
echo "============================================================"

# Check if virtual environment exists
if [ ! -d "$VENV_PATH" ]; then
    echo "❌ Virtual environment not found at $VENV_PATH"
    echo "Please run the setup script first."
    exit 1
fi

cd "$SCRIPT_DIR"

# Read current buffer configuration
BUFFER_MB=$(grep -v "^bits-per-sense" configuration/sensor.dat | cut -d',' -f5)
echo "📋 Current Configuration:"
echo "  Buffer Cap: ${BUFFER_MB} MB"
echo "  Policies: sticky, fifo, roundrobin, random"
echo ""

# Step 1: Run all simulations
echo "🚀 STEP 1: Running Fresh Simulations"
echo "============================================================"

# Build the simulation first (clean rebuild to ensure fresh deps)
echo "🔨 Building simulation (clean rebuild)..."
cd build && make clean && make && cd ..

POLICIES=("sticky" "fifo" "roundrobin" "random")
for policy in "${POLICIES[@]}"; do
    echo ""
    echo "🎯 Running $(echo $policy | tr '[:lower:]' '[:upper:]') policy..."
    echo "------------------------------------------------------------"
    start_time=$(date +%s)
    
    # Clean old logs for this policy
    rm -rf logs/$policy
    mkdir -p logs/$policy
    
    # Run simulation (ignore exit code, check for log files instead)
    ./build/bent_pipe ./configuration/ ./logs/$policy/ $policy || true
    
    end_time=$(date +%s)
    duration=$((end_time - start_time))
    file_count=$(ls -1 logs/$policy/*.csv 2>/dev/null | wc -l)
    
    # Check if simulation actually succeeded by looking for log files
    if [ $file_count -gt 0 ]; then
        echo "  ✅ $(echo $policy | tr '[:lower:]' '[:upper:]') completed! (${duration}s, ${file_count} files)"
    else
        echo "  ❌ $(echo $policy | tr '[:lower:]' '[:upper:]') failed! No log files found."
        exit 1
    fi
done

echo ""
echo "🎉 All simulations completed successfully!"
echo ""

# Step 2: Activate virtual environment for analysis
echo "🔬 STEP 2: Running Comprehensive Analysis"
echo "============================================================"
echo "Activating virtual environment..."
source "$VENV_PATH/bin/activate"

echo ""
echo "Running Complete Analysis Suite (Buffer + Loss + Distribution)..."
echo "------------------------------------------------------------"
start_time=$(date +%s)
python3 run_combined_analysis.py
if [ $? -eq 0 ]; then
    end_time=$(date +%s)
    duration=$((end_time - start_time))
    echo "✅ Complete analysis suite completed successfully! (${duration}s)"
else
    echo "❌ Analysis suite failed!"
    exit 1
fi

echo ""
echo "============================================================"
echo "COMPLETE PIPELINE FINISHED"
echo "============================================================"

# Summary of results
echo "📊 RESULTS SUMMARY:"
echo "  🔧 Fresh simulations run for all 4 policies"
echo "  � Buffer Analysis: buffer_analysis_*/buffer_comparison.png"
echo "  � Data Loss Analysis: loss_analysis_*/loss_comparison.png"
echo "  📦 Complete Logs: */simulation_logs.zip"
echo ""
echo "🎯 Configuration used:"
echo "  Buffer Cap: ${BUFFER_MB} MB"
echo "  Image Size: ~29 MB"
echo "  Satellites: 50"
echo ""
echo "💡 To modify buffer cap, edit configuration/sensor.dat (max-buffer-mb)"
echo "💡 Both plots show orbital passes highlighted in green"
