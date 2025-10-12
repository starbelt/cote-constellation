#!/usr/bin/env python3
"""
Test Script: Single Strategy Chart from Archives
Test the archive processing with just one strategy to verify it works.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path
from datetime import datetime, timedelta
import seaborn as sns
import zipfile
import tempfile
import shutil
import argparse
import glob
import sys

# Configuration
SCRIPT_DIR = Path(__file__).parent.absolute()
POLICIES = ["sticky", "fifo", "roundrobin", "random"]

def extract_constellation_data(folder_path=None):
    """Extract data from constellation_analysis folders"""
    
    if folder_path:
        # User specified a folder
        folder = Path(folder_path)
        
        # Handle relative paths from current directory
        if not folder.is_absolute():
            folder = SCRIPT_DIR / folder
        
        # Validate folder exists and follows naming convention
        if not folder.exists():
            print(f"❌ Error: Specified folder '{folder_path}' does not exist!")
            return None
        
        if not folder.is_dir():
            print(f"❌ Error: '{folder_path}' is not a directory!")
            return None
        
        if not folder.name.startswith('constellation_analysis_'):
            print(f"⚠️  Warning: Folder '{folder.name}' does not follow expected naming convention (constellation_analysis_YYYYMMDD_HHMMSS)")
        
        print(f"📁 Using specified constellation analysis folder: {folder.name}")
        return folder
    else:
        # Find latest folder (existing behavior)
        constellation_folders = [d for d in SCRIPT_DIR.iterdir() 
                               if d.is_dir() and d.name.startswith('constellation_analysis_')]
        
        if not constellation_folders:
            raise FileNotFoundError("No constellation_analysis folders found")
        
        # Sort by folder name (which includes timestamp) to get the latest
        latest_folder = sorted(constellation_folders, key=lambda x: x.name)[-1]
        print(f"📁 Using latest constellation analysis folder: {latest_folder.name}")
        return latest_folder

def extract_archive_data(strategy, archive_base_path):
    """Extract simulation data from zip archive for the given strategy."""
    archive_path = archive_base_path / strategy / 'simulation_logs.zip'
    
    if not archive_path.exists():
        print(f"  Warning: Archive not found: {archive_path}")
        return None
    
    # Create temporary directory
    temp_dir = Path(tempfile.mkdtemp(prefix=f'{strategy}_extract_'))
    
    try:
        # Extract zip file
        print(f"  Extracting {archive_path}...")
        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        
        return temp_dir
    except Exception as e:
        print(f"  Error extracting {archive_path}: {e}")
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        return None

def parse_communication_data_simple(strategy, policy, temp_dir, start_time_str=None, duration_seconds=None):
    """Efficient parsing using visibility_log.csv with optional time filtering."""
    policy_dir = temp_dir / policy
    visibility_log_file = policy_dir / "visibility_log.csv"
    
    if not visibility_log_file.exists():
        print(f"    Warning: No visibility_log.csv found: {visibility_log_file}")
        return None, None, None
        
    # Read visibility log - accurate and efficient
    print(f"    Reading {visibility_log_file}...")
    df = pd.read_csv(visibility_log_file)
    
    if len(df) == 0:
        print(f"    Warning: Empty visibility log")
        return None, None, None
    
    # The 'time' column is already in seconds since start
    # Convert to hours for plotting
    df['hours'] = df['time'] / 3600.0
    
    # Filter by time range if specified (using seconds)
    if start_time_str is not None:
        try:
            # Parse start time (format: HH:MM:SS) and convert to seconds since midnight
            start_hour, start_min, start_sec = map(int, start_time_str.split(':'))
            start_time_seconds = start_hour * 3600 + start_min * 60 + start_sec
            
            # The simulation starts at 13:03:20, which is 13*3600 + 3*60 + 20 = 46,940 seconds since midnight
            # But the 'time' column starts at 0 for the simulation start
            # So we need to find the offset from simulation start to the requested start time
            sim_start_seconds = 13 * 3600 + 3 * 60 + 20  # 13:03:20
            filter_start_offset = start_time_seconds - sim_start_seconds
            
            if duration_seconds:
                filter_end_offset = filter_start_offset + duration_seconds
                print(f"    Filtering data from {start_time_str} to +{duration_seconds}s (offsets {filter_start_offset} to {filter_end_offset} seconds)")
                df = df[(df['time'] >= filter_start_offset) & (df['time'] <= filter_end_offset)]
            else:
                print(f"    Filtering data from {start_time_str} onwards (offset {filter_start_offset} seconds)")
                df = df[df['time'] >= filter_start_offset]
                
            if len(df) == 0:
                print(f"    Warning: No data found in specified time range")
                return None, None, None
                
        except Exception as e:
            print(f"    Warning: Error parsing time filter '{start_time_str}': {e}")
            print("    Using full dataset")
    
    # Get simulation start time from first timestamp if available
    start_time = None
    if 'freshness_timestamp' in df.columns:
        valid_timestamps = df[df['freshness_timestamp'].notna()]['freshness_timestamp']
        if len(valid_timestamps) > 0:
            start_time = pd.to_datetime(valid_timestamps.iloc[0])
    
    # Find all satellites that had connected=1 at any point
    df_connected = df[df['connected'] == 1].copy()
    print(f"    Filtered to {len(df_connected)} connected events (from {len(df)} total)")
    
    connected_sats = df_connected['sat_id'].unique()
    
    if len(connected_sats) == 0:
        # No connections, return empty
        all_hours = df['hours'].unique()
        gs_timeline = pd.DataFrame({'hours': sorted(all_hours)})
        gs_timeline['ground_station_active'] = 0
        return gs_timeline[['hours', 'ground_station_active']], {}, start_time
    
    print(f"    Found {len(connected_sats)} satellites")
    
    # Create complete timeline for each satellite that had connections
    # This includes both connected and disconnected states for proper step plotting
    satellite_data = {}
    
    for sat_id in connected_sats:
        # Get ALL events for this satellite (connected and disconnected)
        sat_all_events = df[df['sat_id'] == sat_id][['hours', 'connected', 'buffer_mb']].copy()
        
        if len(sat_all_events) == 0:
            continue
        
        # Sort by time
        sat_all_events = sat_all_events.sort_values('hours').reset_index(drop=True)
        
        # Set connection state
        sat_all_events[f'sat_{sat_id}_connected'] = sat_all_events['connected']
        
        # Buffer state: 1 if buffer > 0.001, 0 if empty (only meaningful when connected)
        sat_all_events[f'sat_{sat_id}_has_buffer'] = (sat_all_events['buffer_mb'] > 0.001).astype(int)
        
        satellite_data[sat_id] = sat_all_events
    
    # Ground station timeline: active when ANY satellite is connected
    gs_active_hours = df_connected['hours'].unique()
    all_hours = df['hours'].unique()
    gs_timeline = pd.DataFrame({'hours': sorted(all_hours)})
    gs_timeline['ground_station_active'] = gs_timeline['hours'].isin(gs_active_hours).astype(int)
    
    return gs_timeline[['hours', 'ground_station_active']], satellite_data, start_time

def test_single_strategy(strategy="close-spaced", policy="sticky", start_time_str=None, duration_seconds=None, constellation_folder=None):
    """Test processing a single strategy with optional parameters."""
    print(f"Testing {strategy} strategy...")
    
    # Use the provided constellation analysis directory or find latest
    if constellation_folder is None:
        archive_base_path = extract_constellation_data()
        if not archive_base_path:
            return None
    else:
        archive_base_path = constellation_folder
    
    # Extract archive data
    temp_dir = extract_archive_data(strategy, archive_base_path)
    if temp_dir is None:
        return None
    
    try:
        print(f"  Testing {policy} policy...")
        
        ground_data, satellite_data, start_time = parse_communication_data_simple(
            strategy, policy, temp_dir, start_time_str, duration_seconds)
        
        if ground_data is None:
            print(f"  No data found for {strategy}/{policy}")
            return None
        
        print(f"  ✅ Successfully parsed data:")
        print(f"    - Ground data: {len(ground_data)} rows")
        print(f"    - Satellite data: {len(satellite_data)} satellites")
        print(f"    - Time range: {ground_data['hours'].min():.2f} to {ground_data['hours'].max():.2f} hours")
        
        # Calculate figure width based on time duration
        time_duration_hours = ground_data['hours'].max() - ground_data['hours'].min()
        if time_duration_hours <= 0.5:  # 30 minutes or less
            fig_width = 16
        elif time_duration_hours <= 2.0:  # 2 hours or less
            fig_width = 24
        elif time_duration_hours <= 6.0:  # 6 hours or less
            fig_width = 32
        else:  # More than 6 hours
            fig_width = min(48, int(16 + time_duration_hours * 4))  # Scale with time, max 48
        
        print(f"    - Chart width: {fig_width} (for {time_duration_hours:.2f} hours)")
        
        # Create a tall chart with vertical legend - width scales with time duration
        fig, ax = plt.subplots(1, 1, figsize=(fig_width, 12))  # Height stays at 12
        
        # Plot ground station with taller scale
        ax.plot(ground_data['hours'], ground_data['ground_station_active'] * 1.5, 
               'k-', linewidth=2, label='Ground Station')
        
        # Plot satellites with buffer-aware coloring (keeping proper up/down flipping)
        colors = ['#E74C3C', '#3498DB', '#2ECC71', '#F39C12', '#9B59B6', 
                 '#E67E22', '#8E44AD', '#1ABC9C', '#F1C40F', '#34495E'] * 5  # Repeat for many satellites
        
        for i, (sat_id, sat_data) in enumerate(satellite_data.items()):
            # Satellites with slightly expanded range for better visual fill
            sat_baseline = 2.0  # Satellite "0" position (idle) - lower baseline
            sat_active = 3.5    # Satellite "1" position (active) - taller section
            
            # Binary positioning - no offsets, strictly on the lines
            y_line = sat_data[f'sat_{sat_id}_connected'] * 1.5 + sat_baseline  # 1.5 scale for taller sections
            sat_color = colors[i % len(colors)]
            
            # Track if we've added labels for this satellite
            active_labeled = False
            hogging_labeled = False
            
            # Check if we have buffer state data for intelligent coloring
            buffer_col = f'sat_{sat_id}_has_buffer'
            if buffer_col in sat_data.columns:
                # Create a single line but with different colors for different segments
                
                # Create arrays to hold the line data
                hours = sat_data['hours'].values
                y_values = y_line.values
                
                # Plot the line in segments based on state
                for j in range(len(hours) - 1):
                    x_segment = [hours[j], hours[j+1]]
                    y_segment = [y_values[j], y_values[j+1]]
                    
                    # Determine color based on state
                    if sat_data.iloc[j][f'sat_{sat_id}_connected'] == 1:  # Connected
                        if sat_data.iloc[j][buffer_col] == 1:  # Has buffer
                            color = sat_color
                            sat_label = str(sat_id)[-1] if len(str(sat_id)) > 10 else str(sat_id)
                            label = f'Sat {sat_label} (Active)' if not active_labeled else ''
                            if not active_labeled:
                                active_labeled = True
                        else:  # No buffer (hogging)
                            color = 'grey'
                            sat_label = str(sat_id)[-1] if len(str(sat_id)) > 10 else str(sat_id)
                            label = f'Sat {sat_label} (Hogging)' if not hogging_labeled else ''
                            if not hogging_labeled:
                                hogging_labeled = True
                    else:  # Disconnected
                        color = sat_color
                        label = ''
                    
                    ax.plot(x_segment, y_segment, 
                           color=color, linewidth=2, alpha=0.8 if color != 'grey' else 0.6,
                           label=label if label else '')
            else:
                # Fallback: original simple plotting
                ax.plot(sat_data['hours'], y_line, 
                       color=sat_color, linewidth=2, label=f'Sat {sat_id}', alpha=0.8)
        
        # Create title with time range information if specified
        if start_time_str and duration_seconds:
            end_time = datetime.strptime(start_time_str, '%H:%M:%S') + timedelta(seconds=duration_seconds)
            title = f'{strategy} - {policy} ({start_time_str} plus {duration_seconds} seconds)'
        elif start_time_str:
            title = f'{strategy} - {policy} (from {start_time_str} onwards)'
        else:
            title = f'{strategy} - {policy} (first 1000 rows)'
        
        ax.set_title(title, fontsize=14, fontweight='bold')
        ax.set_ylabel('Activity')
        ax.grid(True, alpha=0.3)
        
        # Format x-axis with actual timestamps
        # Convert hours back to timestamps for x-axis labels
        num_ticks = 6  # Number of x-axis labels
        hour_ticks = np.linspace(ground_data['hours'].min(), ground_data['hours'].max(), num_ticks)
        timestamp_ticks = [start_time + pd.Timedelta(hours=h) for h in hour_ticks]
        
        ax.set_xticks(hour_ticks)
        ax.set_xticklabels([ts.strftime('%H:%M:%S') for ts in timestamp_ticks], rotation=45)
        ax.set_xlabel('Time (HH:MM:SS)')
        
        # Set y-axis limits and custom labels with taller matching sections
        ax.set_ylim(-0.2, 4.0)
        ax.set_yticks([0, 1.5, 2.0, 3.5])
        ax.set_yticklabels(['GS Idle', 'GS Active', 'Sat Idle', 'Sat Active'])
        
        # Add reference lines
        ax.axhline(y=0, color='gray', linestyle='--', alpha=0.3)
        ax.axhline(y=1.5, color='gray', linestyle='--', alpha=0.3)
        ax.axhline(y=2.0, color='gray', linestyle='--', alpha=0.3)
        ax.axhline(y=3.5, color='gray', linestyle='--', alpha=0.3)
        
        # Add vertical legend that spans the chart height
        handles, labels = ax.get_legend_handles_labels()
        if len(handles) > 0:
            # Single column vertical legend positioned to the right
            ax.legend(bbox_to_anchor=(1.02, 1), loc='upper left', fontsize=8, ncol=1)
        
        # Save test chart to constellation analysis folder
        output_dir = archive_base_path
        
        # Create filename with time range info if custom time was specified
        if start_time_str and duration_seconds:
            end_time = datetime.strptime(start_time_str, '%H:%M:%S') + timedelta(seconds=duration_seconds)
            time_suffix = f"_{start_time_str.replace(':', '')}-{end_time.strftime('%H%M%S')}"
        elif start_time_str:
            time_suffix = f"_{start_time_str.replace(':', '')}plus"
        else:
            time_suffix = ""
            
        output_file = output_dir / f"active_idle_timeseries_zoom_{strategy}_{policy}{time_suffix}.png"
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        plt.close()
        
        print(f"  ✅ Test chart saved: {output_file}")
        return output_file
        
    finally:
        # Clean up
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
            print("  ✅ Cleaned up temporary files")

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Generate satellite communication charts from archived data')
    parser.add_argument('folder', nargs='?', default=None, 
                       help='Constellation analysis folder to process (optional, defaults to latest)')
    parser.add_argument('strategy', nargs='?', default='close-spaced',
                       help='Strategy to analyze (default: close-spaced)')
    parser.add_argument('policy', nargs='?', default='sticky',
                       help='Policy to analyze (default: sticky)')
    parser.add_argument('start_time', nargs='?', default=None,
                       help='Start time in HH:MM:SS format (default: use first 1000 rows)')
    parser.add_argument('duration', nargs='?', type=int, default=None,
                       help='Duration in seconds (default: no limit if start_time specified)')
    parser.add_argument('--runforseconds', type=int, default=None,
                       help='Run simulation for specified seconds before generating charts (requires specific folder)')
    
    return parser.parse_args()

def run_simulation_and_generate_charts(folder_name, runforseconds, strategy, policy, start_time, duration):
    """Run simulation for specified duration and then generate charts"""
    
    # Validate folder exists
    folder_path = SCRIPT_DIR / folder_name
    if not folder_path.exists():
        print(f"❌ Error: Folder '{folder_name}' does not exist!")
        return
    
    if not folder_path.is_dir():
        print(f"❌ Error: '{folder_name}' is not a directory!")
        return
    
    # Extract parameters from folder name
    parts = folder_name.split('_')
    if len(parts) < 6:
        print(f"❌ Error: Folder name '{folder_name}' doesn't follow expected format:")
        print("   Expected: constellation_analysis_YYYYMMDD_HHMMSS_IMAGESIZE_SATCOUNT")
        return
    
    try:
        size_part = parts[4]  # e.g., "00027" or "28000"
        sat_part = parts[5]   # e.g., "01" or "200"
        
        image_size = int(size_part) / 1000.0  # Convert back to MB
        sat_count = int(sat_part)
        
        print(f"📁 Running simulation for folder: {folder_name}")
        print(f"   Image size: {image_size:.3f}MB")
        print(f"   Satellite count: {sat_count}")
        print(f"   Duration: {runforseconds} seconds ({runforseconds/3600:.1f} hours)")
        print(f"   Chart params: strategy={strategy}, policy={policy}")
        print()
        
    except (ValueError, IndexError):
        print(f"❌ Error: Could not parse parameters from folder name '{folder_name}'")
        return
    
    # Look for run_simulation.sh script
    run_script = folder_path / "run_simulation.sh"
    if not run_script.exists():
        print(f"❌ Error: No run_simulation.sh script found in {folder_name}")
        print("   Expected to find: run_simulation.sh")
        return
    
    print(f"🚀 Starting simulation...")
    print(f"   Script: {run_script}")
    print(f"   Duration: {runforseconds} seconds")
    print()
    
    # Run the simulation
    import subprocess
    import time
    
    try:
        # Change to the folder directory and run the simulation
        process = subprocess.Popen(
            ["bash", "run_simulation.sh", str(runforseconds)],
            cwd=folder_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        print("⏱️  Simulation running... (this may take a while)")
        start_time_sim = time.time()
        
        # Wait for completion
        stdout, stderr = process.communicate()
        end_time_sim = time.time()
        elapsed = end_time_sim - start_time_sim
        
        if process.returncode == 0:
            print(f"✅ Simulation completed successfully in {elapsed:.1f} seconds")
            if stdout:
                print("Simulation output:")
                print(stdout)
        else:
            print(f"❌ Simulation failed with return code {process.returncode}")
            if stderr:
                print("Error output:")
                print(stderr)
            return
        
    except Exception as e:
        print(f"❌ Error running simulation: {e}")
        return
    
    print()
    print("📊 Generating chart from simulation results...")
    
    # Now generate chart for the specific strategy and policy
    print(f"  Processing {strategy} strategy with {policy} policy...")
    test_single_strategy(strategy, policy, start_time, duration, folder_path)
    
    return True

def main():
    args = parse_arguments()
    
    # If runforseconds is specified, we need a specific folder
    if args.runforseconds is not None:
        if args.folder is None:
            print("❌ Error: --runforseconds requires a specific folder to be specified")
            print("   Example: python active_idle_timeseries_zoom.py constellation_analysis_20251007_234546_28000_200 close-spaced sticky --runforseconds 3600")
            return
        
        # Run simulation first, then generate charts
        return run_simulation_and_generate_charts(args.folder, args.runforseconds, args.strategy, args.policy, args.start_time, args.duration)
    
    # Regular processing mode
    # Extract constellation analysis data
    constellation_folder = extract_constellation_data(args.folder)
    if not constellation_folder:
        return
    
    print("Testing single strategy chart generation...")
    print(f"Parameters: strategy={args.strategy}, policy={args.policy}, start_time={args.start_time}, duration={args.duration}")
    
    test_single_strategy(args.strategy, args.policy, args.start_time, args.duration, constellation_folder)

if __name__ == "__main__":
    main()
