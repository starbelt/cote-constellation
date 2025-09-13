#!/usr/bin/env python3
"""
Combined Multi-Satellite Analysis Suite

Generates buffer usage, data loss, and satellite distribution analysis
all in one timestamped folder with log archive.
"""

import subprocess
import sys
import shutil
import zipfile
from pathlib import Path
from datetime import datetime

def create_log_archive(output_dir):
    """Create a zip archive of all simulation logs"""
    script_dir = Path(__file__).parent.absolute()
    logs_dir = script_dir / "logs"
    policies = ["sticky", "fifo", "roundrobin", "random"]
    
    archive_path = output_dir / "simulation_logs.zip"
    
    with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for policy in policies:
            policy_dir = logs_dir / policy
            if policy_dir.exists():
                for log_file in policy_dir.glob("*.csv"):
                    # Add file to zip with policy folder structure
                    arcname = f"{policy}/{log_file.name}"
                    zipf.write(log_file, arcname)
    
    print(f"Created log archive: {archive_path}")
    return archive_path

def main():
    """Run complete analysis suite"""
    script_dir = Path(__file__).parent.absolute()
    
    print("=" * 70)
    print("COMPREHENSIVE MULTI-SATELLITE CONSTELLATION ANALYSIS SUITE")
    print("=" * 70)
    
    # Create single timestamped output directory for all analyses
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = script_dir / f"constellation_analysis_{timestamp}"
    output_dir.mkdir(exist_ok=True)
    
    print(f"\n📁 Creating unified analysis folder: {output_dir.name}")
    
    scripts_to_run = [
        ("Buffer Analysis", "multi_satellite_buffer_plot.py", ["buffer_comparison.png"]),
        ("Data Loss Analysis", "multi_satellite_loss_plot.py", ["loss_comparison.png"]),
        ("Distribution Analysis", "multi_satellite_distribution_bars.py", ["satellite_distribution_bars.png"]),
        ("Loss Summary", "multi_satellite_loss_bars.py", ["satellite_loss_bars.png"]),
        ("Idle Time Analysis", "multi_satellite_idle_plot.py", ["idle_time_comparison.png", "idle_time_bars.png"]),
        ("Idle Time Summary", "multi_satellite_idle_bars.py", ["satellite_idle_bars.png"])
    ]
    
    success_count = 0
    
    # Run all analysis scripts
    for i, (name, script_name, output_files) in enumerate(scripts_to_run, 1):
        print(f"\n{i}. Running {name}...")
        script_path = script_dir / script_name
        
        try:
            result = subprocess.run([sys.executable, str(script_path)], 
                                  capture_output=True, text=True, cwd=script_dir)
            if result.returncode == 0:
                print(f"✅ {name} completed successfully!")
                success_count += 1
                
                # Find the most recent analysis folder and move the output
                analysis_folders = list(script_dir.glob("*analysis_*"))
                if analysis_folders:
                    # Get the most recent folder (excluding our target folder)
                    recent_folders = [f for f in analysis_folders if f != output_dir]
                    if recent_folders:
                        most_recent = max(recent_folders, key=lambda x: x.stat().st_mtime)
                        
                        # Move the PNG files to our unified folder
                        for output_file in output_files:
                            source_png = most_recent / output_file
                            if source_png.exists():
                                shutil.move(str(source_png), str(output_dir / output_file))
                                print(f"   📊 Moved {output_file} to unified analysis folder")
                        
                        # Clean up the individual analysis folder if it's empty
                        try:
                            if not any(most_recent.iterdir()):
                                most_recent.rmdir()
                            elif len(list(most_recent.iterdir())) == 1 and (most_recent / "simulation_logs.zip").exists():
                                # Only has log archive, we'll create our own
                                (most_recent / "simulation_logs.zip").unlink()
                                most_recent.rmdir()
                        except:
                            pass  # Don't fail if cleanup doesn't work
                            
                if result.stdout:
                    print(f"   {result.stdout.strip()}")
            else:
                print(f"❌ {name} failed!")
                if result.stderr:
                    print(f"   Error: {result.stderr}")
        except Exception as e:
            print(f"❌ Error running {name}: {e}")
    
    # Create unified log archive
    print(f"\n📦 Creating unified log archive...")
    create_log_archive(output_dir)
    
    # Final summary
    print(f"\n{'='*70}")
    print(f"ANALYSIS COMPLETE!")
    print(f"{'='*70}")
    print(f"📁 Output folder: {output_dir}")
    print(f"✅ Successfully generated: {success_count}/{len(scripts_to_run)} analyses")
    
    # List contents
    contents = list(output_dir.iterdir())
    if contents:
        print(f"\n📋 Generated files:")
        for item in sorted(contents):
            if item.is_file():
                size_mb = item.stat().st_size / (1024 * 1024)
                if item.suffix == '.png':
                    print(f"   📊 {item.name} ({size_mb:.1f} MB)")
                elif item.suffix == '.zip':
                    print(f"   📦 {item.name} ({size_mb:.1f} MB)")
                else:
                    print(f"   📄 {item.name} ({size_mb:.1f} MB)")
    
    print(f"\n🎯 All constellation analysis complete! Check: {output_dir.name}")

if __name__ == "__main__":
    main()
