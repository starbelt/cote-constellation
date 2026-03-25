#!/bin/bash
#
# run_temporal_analysis.sh
#
# Automated script to run complete temporal and geographic analysis
# of satellite link policy simulation results
#
# Usage: ./run_temporal_analysis.sh [results_dir]
#

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${1:-${SCRIPT_DIR}/results}"

echo "=============================================================================="
echo "Temporal and Geographic Analysis for Satellite Link Policies"
echo "=============================================================================="
echo ""
echo "Results directory: ${RESULTS_DIR}"
echo ""

# Check if results directory exists
if [ ! -d "${RESULTS_DIR}" ]; then
    echo "ERROR: Results directory not found: ${RESULTS_DIR}"
    echo "Usage: $0 [results_dir]"
    exit 1
fi

# Check for Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: python3 not found. Please install Python 3."
    exit 1
fi

# Check for required Python packages
echo "[1/4] Checking dependencies..."
python3 -c "import pandas, numpy, matplotlib, seaborn, scipy" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "ERROR: Missing required Python packages."
    echo "Install with: pip install pandas numpy matplotlib seaborn scipy"
    exit 1
fi
echo "✓ All dependencies installed"
echo ""

# Run geographic coverage analysis
echo "[2/4] Running geographic coverage analysis..."
echo "----------------------------------------------------------------------"
python3 "${SCRIPT_DIR}/temporal_geographic_analysis.py"
if [ $? -eq 0 ]; then
    echo "✓ Geographic analysis complete"
else
    echo "✗ Geographic analysis failed"
    exit 1
fi
echo ""

# Run temporal pattern analysis
echo "[3/4] Running temporal pattern analysis..."
echo "----------------------------------------------------------------------"
python3 "${SCRIPT_DIR}/temporal_pattern_analysis.py"
if [ $? -eq 0 ]; then
    echo "✓ Temporal pattern analysis complete"
else
    echo "✗ Temporal pattern analysis failed"
    exit 1
fi
echo ""

# Generate summary report
echo "[4/4] Generating summary report..."
echo "----------------------------------------------------------------------"

OUTPUT_DIRS=(
    "${SCRIPT_DIR}/temporal_geographic_analysis"
    "${SCRIPT_DIR}/temporal_pattern_analysis"
)

SUMMARY_FILE="${SCRIPT_DIR}/analysis_summary.txt"

cat > "${SUMMARY_FILE}" << EOF
================================================================================
Temporal and Geographic Analysis Summary
================================================================================
Generated: $(date)
Results Directory: ${RESULTS_DIR}

Analysis Outputs:
--------------------------------------------------------------------------------

1. Geographic Coverage Analysis
   Location: temporal_geographic_analysis/
   
   CSV Files:
   - geographic_coverage_summary.csv    # Coverage and equity metrics
   - revisit_time_summary.csv           # Time between location revisits
   - image_downlink_latency_summary.csv # Capture-to-downlink latency
   
   Visualizations:
   - geographic_equity_gini.png         # Gini coefficient comparison
   - coverage_extent.png                # Unique cells covered
   - revisit_time_analysis.png          # Revisit time comparison
   - heatmaps/*.png                     # Geographic coverage heatmaps

2. Temporal Pattern Analysis
   Location: temporal_pattern_analysis/
   
   CSV Files:
   - coverage_gaps.csv                  # Maximum coverage gaps
   - service_windows.csv                # Connection duration statistics
   - data_freshness.csv                 # Capture-to-downlink timing
   - temporal_fairness.csv              # Service distribution over time
   
   Visualizations:
   - coverage_gaps_analysis.png         # Gap duration comparison
   - freshness_analysis.png             # Data freshness comparison
   - service_window_analysis.png        # Window duration comparison

Key Metrics:
--------------------------------------------------------------------------------

Geographic Equity (Gini Coefficient):
  Lower is better (0 = perfect equality, 1 = perfect inequality)
  
Coverage Extent:
  Number of unique 5°x5° geographic cells observed
  
Revisit Time:
  Time between successive observations of same location
  
Data Freshness:
  Time from image capture to successful downlink
  
Coverage Gaps:
  Maximum time without observing a location
  
Service Windows:
  Duration of continuous satellite-ground connections

Usage Notes:
--------------------------------------------------------------------------------

1. Review CSV files for detailed numerical results
2. Examine PNG visualizations for trends and comparisons
3. Use heatmaps to identify geographic biases
4. Compare configurations to find optimal trade-offs

For more information, see TEMPORAL_ANALYSIS_README.md

================================================================================
EOF

echo "✓ Summary report generated: ${SUMMARY_FILE}"
echo ""

# Display file counts
echo "=============================================================================="
echo "Analysis Complete!"
echo "=============================================================================="
echo ""

for dir in "${OUTPUT_DIRS[@]}"; do
    if [ -d "${dir}" ]; then
        csv_count=$(find "${dir}" -name "*.csv" | wc -l | tr -d ' ')
        png_count=$(find "${dir}" -name "*.png" | wc -l | tr -d ' ')
        echo "$(basename ${dir}):"
        echo "  - ${csv_count} CSV files"
        echo "  - ${png_count} PNG visualizations"
        echo ""
    fi
done

echo "Summary report: ${SUMMARY_FILE}"
echo ""
echo "Next steps:"
echo "  1. Review CSV files for numerical results"
echo "  2. Examine PNG visualizations for trends"
echo "  3. Generate additional heatmaps if needed"
echo "  4. Integrate findings into paper"
echo ""
echo "=============================================================================="
