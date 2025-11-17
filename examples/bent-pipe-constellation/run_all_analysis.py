#!/usr/bin/env python3
"""
Run all analysis scripts sequentially with error handling and reporting.

This script will:
1. Execute every plot_*.py script in the bent-pipe-constellation directory
2. Capture crashes and log them to crash_log.txt
3. Continue execution even if scripts fail
4. Generate a final report in report_log.txt with pass/fail status
"""

import subprocess
import sys
from pathlib import Path
from datetime import datetime
import traceback

def run_script(script_path):
    """
    Run a single Python script and return success status and output.
    
    Args:
        script_path: Path to the Python script to run
        
    Returns:
        tuple: (success: bool, output: str, error: str, duration: float)
    """
    start_time = datetime.now()
    
    try:
        # Run the script with timeout of 30 minutes per script
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=script_path.parent,
            capture_output=True,
            text=True,
            timeout=1800  # 30 minutes timeout
        )
        
        duration = (datetime.now() - start_time).total_seconds()
        
        # Check if script succeeded (exit code 0)
        success = result.returncode == 0
        
        return success, result.stdout, result.stderr, duration
        
    except subprocess.TimeoutExpired:
        duration = (datetime.now() - start_time).total_seconds()
        return False, "", f"Script timed out after 30 minutes", duration
        
    except Exception as e:
        duration = (datetime.now() - start_time).total_seconds()
        return False, "", f"Exception: {str(e)}\n{traceback.format_exc()}", duration


def main():
    """Main execution function."""
    
    # Setup paths
    script_dir = Path(__file__).parent
    analysis_dir = script_dir / "constellation_analysis"
    analysis_dir.mkdir(exist_ok=True)
    
    crash_log_path = analysis_dir / "crash_log.txt"
    report_log_path = analysis_dir / "report_log.txt"
    
    # Find all analysis scripts
    plot_scripts = sorted(script_dir.glob("plot_*.py"))
    generate_scripts = sorted(script_dir.glob("generate_combined_*.py"))
    multi_scripts = sorted(script_dir.glob("multi_satellite_*.py"))
    
    # Combine all scripts
    all_scripts = plot_scripts + generate_scripts + multi_scripts
    
    print("="*80)
    print("CONSTELLATION ANALYSIS - BATCH EXECUTION")
    print("="*80)
    print(f"Found {len(all_scripts)} analysis scripts to run:")
    print(f"  - {len(plot_scripts)} plot_*.py scripts")
    print(f"  - {len(generate_scripts)} generate_combined_*.py scripts")
    print(f"  - {len(multi_scripts)} multi_satellite_*.py scripts")
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Crash log: {crash_log_path}")
    print(f"Report log: {report_log_path}")
    print("="*80)
    print()
    
    # Track results
    results = []
    total_duration = 0
    
    # Clear previous logs
    crash_log_path.write_text("")
    
    # Run each script
    for i, script_path in enumerate(all_scripts, 1):
        script_name = script_path.name
        
        print(f"[{i}/{len(all_scripts)}] Running: {script_name}")
        print("-" * 80)
        
        success, stdout, stderr, duration = run_script(script_path)
        total_duration += duration
        
        # Store result
        result = {
            'script': script_name,
            'success': success,
            'duration': duration,
            'stdout': stdout,
            'stderr': stderr
        }
        results.append(result)
        
        if success:
            print(f"✅ SUCCESS ({duration:.1f}s)")
            # Show last few lines of output
            if stdout:
                lines = stdout.strip().split('\n')
                last_lines = lines[-3:] if len(lines) > 3 else lines
                for line in last_lines:
                    print(f"   {line}")
        else:
            print(f"❌ FAILED ({duration:.1f}s)")
            print(f"   Error: {stderr[:200]}")
            
            # Log crash details
            with open(crash_log_path, 'a') as f:
                f.write("="*80 + "\n")
                f.write(f"CRASH: {script_name}\n")
                f.write(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Duration: {duration:.1f}s\n")
                f.write("="*80 + "\n")
                f.write("\nSTDERR:\n")
                f.write(stderr + "\n")
                f.write("\nSTDOUT:\n")
                f.write(stdout + "\n")
                f.write("\n\n")
        
        print()
    
    # Generate final report
    print("="*80)
    print("GENERATING FINAL REPORT")
    print("="*80)
    
    passed = [r for r in results if r['success']]
    failed = [r for r in results if not r['success']]
    
    report_lines = []
    report_lines.append("="*80)
    report_lines.append("CONSTELLATION ANALYSIS - BATCH EXECUTION REPORT")
    report_lines.append("="*80)
    report_lines.append(f"Execution Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(f"Total Duration: {total_duration/60:.1f} minutes ({total_duration:.1f} seconds)")
    report_lines.append(f"Total Scripts: {len(results)}")
    report_lines.append(f"Passed: {len(passed)}")
    report_lines.append(f"Failed: {len(failed)}")
    report_lines.append("="*80)
    report_lines.append("")
    
    # Passed scripts
    if passed:
        report_lines.append("✅ PASSED SCRIPTS:")
        report_lines.append("-"*80)
        for r in passed:
            report_lines.append(f"  ✓ {r['script']:<60} ({r['duration']:>6.1f}s)")
        report_lines.append("")
    
    # Failed scripts
    if failed:
        report_lines.append("❌ FAILED SCRIPTS:")
        report_lines.append("-"*80)
        for r in failed:
            report_lines.append(f"  ✗ {r['script']:<60} ({r['duration']:>6.1f}s)")
            # Show first line of error
            error_line = r['stderr'].split('\n')[0] if r['stderr'] else "Unknown error"
            report_lines.append(f"    Error: {error_line[:70]}")
        report_lines.append("")
        report_lines.append(f"See {crash_log_path.name} for full error details")
        report_lines.append("")
    
    # Summary by duration
    report_lines.append("⏱️  EXECUTION TIME BREAKDOWN:")
    report_lines.append("-"*80)
    sorted_by_time = sorted(results, key=lambda x: x['duration'], reverse=True)
    for r in sorted_by_time:
        status = "✓" if r['success'] else "✗"
        report_lines.append(f"  {status} {r['script']:<60} {r['duration']:>6.1f}s")
    report_lines.append("")
    
    # Write report to file
    report_text = '\n'.join(report_lines)
    report_log_path.write_text(report_text)
    
    # Print report to console
    print(report_text)
    
    print("="*80)
    print(f"Report saved to: {report_log_path}")
    if failed:
        print(f"Crash details saved to: {crash_log_path}")
    print("="*80)
    
    # Exit with appropriate code
    sys.exit(0 if len(failed) == 0 else 1)


if __name__ == "__main__":
    main()
