#!/usr/bin/env python3
"""
Combined Buffer and Data Loss Analysis

Generates both buffer usage and cumulative data loss plots.
"""

import subprocess
import sys
from pathlib import Path

def main():
    """Run both buffer and loss analysis"""
    script_dir = Path(__file__).parent.absolute()
    
    print("=" * 60)
    print("COMBINED BUFFER AND DATA LOSS ANALYSIS")
    print("=" * 60)
    
    # Run buffer analysis
    print("\n1. Running Buffer Analysis...")
    buffer_script = script_dir / "multi_satellite_buffer_plot.py"
    try:
        result = subprocess.run([sys.executable, str(buffer_script)], 
                              capture_output=True, text=True, cwd=script_dir)
        if result.returncode == 0:
            print("✅ Buffer analysis completed successfully!")
            if result.stdout:
                print(result.stdout)
        else:
            print("❌ Buffer analysis failed!")
            if result.stderr:
                print("Error:", result.stderr)
    except Exception as e:
        print(f"❌ Error running buffer analysis: {e}")
    
    # Run loss analysis
    print("\n2. Running Data Loss Analysis...")
    loss_script = script_dir / "multi_satellite_loss_plot.py"
    try:
        result = subprocess.run([sys.executable, str(loss_script)], 
                              capture_output=True, text=True, cwd=script_dir)
        if result.returncode == 0:
            print("✅ Data loss analysis completed successfully!")
            if result.stdout:
                print(result.stdout)
        else:
            print("❌ Data loss analysis failed!")
            if result.stderr:
                print("Error:", result.stderr)
    except Exception as e:
        print(f"❌ Error running loss analysis: {e}")
    
    print("\n" + "=" * 60)
    print("ANALYSIS COMPLETE")
    print("=" * 60)
    print("Check the generated directories for:")
    print("  • buffer_analysis_YYYYMMDD_HHMMSS/buffer_comparison.png")
    print("  • loss_analysis_YYYYMMDD_HHMMSS/loss_comparison.png")
    print("  • simulation_logs.zip (archived logs)")

if __name__ == "__main__":
    main()
