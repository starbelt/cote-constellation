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

# Configuration
SCRIPT_DIR = Path(__file__).parent.absolute()
POLICIES = ["sticky", "fifo", "roundrobin", "random"]

def find_latest_constellation_analysis_folder(script_dir):
    """Find the most recent constellation_analysis folder."""
    constellation_folders = [d for d in script_dir.iterdir() 
                           if d.is_dir() and d.name.startswith('constellation_analysis_')]
    
    if not constellation_folders:
        raise FileNotFoundError("No constellation_analysis folders found")
    
    # Sort by folder name (which includes timestamp) to get the latest
    latest_folder = sorted(constellation_folders, key=lambda x: x.name)[-1]
    print(f"  Using constellation analysis folder: {latest_folder.name}")
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
    """Simplified parsing for testing with optional time filtering."""
    policy_dir = temp_dir / policy
    tx_rx_file = policy_dir / "meas-downlink-tx-rx.csv"
    
    if not tx_rx_file.exists():
        print(f"    Warning: No tx-rx file found: {tx_rx_file}")
        return None, None, None
        
    # Read the data - if no time filtering specified, limit to first 1000 rows for testing
    print(f"    Reading {tx_rx_file}...")
    if start_time_str is None and duration_seconds is None:
        df = pd.read_csv(tx_rx_file, nrows=1000)  # Default behavior
        print("    Using default: first 1000 rows for testing")
    else:
        df = pd.read_csv(tx_rx_file)  # Read full file for time filtering
        print(f"    Read full file ({len(df)} rows) for time filtering")
    
    # Handle the empty third column
    if len(df.columns) == 3:
        df = df.iloc[:, :2]
    
    if len(df) <= 1:
        print(f"    Warning: Empty data file")
        return None, None, None
        
    df.columns = ['timestamp', 'satellite']
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Filter by time range if specified
    if start_time_str is not None:
        try:
            # Parse start time (format: HH:MM:SS)
            start_hour, start_min, start_sec = map(int, start_time_str.split(':'))
            
            # Get the simulation start date and apply the specified time
            sim_start_date = df['timestamp'].min().date()
            filter_start_time = datetime.combine(sim_start_date, 
                                                datetime.min.time().replace(hour=start_hour, 
                                                                          minute=start_min, 
                                                                          second=start_sec))
            
            if duration_seconds:
                filter_end_time = filter_start_time + timedelta(seconds=duration_seconds)
                print(f"    Filtering data from {filter_start_time.strftime('%H:%M:%S')} to {filter_end_time.strftime('%H:%M:%S')} ({duration_seconds} seconds)")
                df = df[(df['timestamp'] >= filter_start_time) & (df['timestamp'] <= filter_end_time)]
            else:
                print(f"    Filtering data from {filter_start_time.strftime('%H:%M:%S')} onwards")
                df = df[df['timestamp'] >= filter_start_time]
                
            if len(df) == 0:
                print(f"    Warning: No data found in specified time range")
                return None, None, None
                
        except Exception as e:
            print(f"    Warning: Error parsing time filter '{start_time_str}': {e}")
            print("    Using full dataset")
    
    # Convert to relative time (hours from start)
    start_time = df['timestamp'].min()
    df['hours'] = (df['timestamp'] - start_time).dt.total_seconds() / 3600
    
    # Ground station state
    df['ground_station_active'] = df['satellite'].apply(lambda x: 0 if pd.isna(x) or x == 'None' else 1)
    
    # Find active satellites
    active_data = df[df['satellite'] != 'None']
    if len(active_data) == 0:
        return df[['hours', 'ground_station_active']], {}
        
    # Get all satellites that connect during this window
    satellite_counts = active_data['satellite'].value_counts()
    all_active_sats = satellite_counts.index.tolist()
    
    print(f"    Found {len(satellite_counts)} satellites, using all {len(all_active_sats)}")
    
    # Create simplified satellite data with buffer state simulation
    satellite_data = {}
    for sat in all_active_sats:
        sat_connected = df['satellite'].apply(lambda x: 1 if x == sat else 0)
        sat_data = df[['hours']].copy()
        sat_data[f'sat_{sat}_connected'] = sat_connected
        
        # Simulate buffer state: satellites drain buffer quickly then stay connected with buffer=0
        sat_data[f'sat_{sat}_has_buffer'] = 0  # Default: no buffer
        
        # Find connection start points
        connected_diff = sat_connected.diff()
        connection_starts = sat_data[connected_diff == 1].index
        
        # For each connection, assume buffer drains quickly (first 10-20% of connection time)
        for start_idx in connection_starts:
            # Find when this connection period ends
            remaining_data = sat_data.loc[start_idx:]
            disconnection = remaining_data[remaining_data[f'sat_{sat}_connected'] == 0]
            
            if len(disconnection) > 0:
                end_idx = disconnection.index[0]
            else:
                end_idx = len(sat_data) - 1
            
            # Buffer drains in first 15% of connection time, then buffer=0 (hogging)
            connection_duration = end_idx - start_idx
            buffer_duration = max(2, int(connection_duration * 0.15))  # 15% with buffer
            
            # Set buffer=1 for early part of connection
            sat_data.loc[start_idx:start_idx + buffer_duration, f'sat_{sat}_has_buffer'] = 1
        
        satellite_data[sat] = sat_data
    
    return df[['hours', 'ground_station_active']], satellite_data, start_time

def test_single_strategy(strategy="bent-pipe", policy="sticky", start_time_str=None, duration_seconds=None):
    """Test processing a single strategy with optional parameters."""
    print(f"Testing {strategy} strategy...")
    
    # Use the latest constellation analysis directory
    archive_base_path = find_latest_constellation_analysis_folder(SCRIPT_DIR)
    
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
                            label = f'Sat {sat_id[-1] if len(sat_id) > 10 else sat_id} (Active)' if not active_labeled else ''
                            if not active_labeled:
                                active_labeled = True
                        else:  # No buffer (hogging)
                            color = 'grey'
                            label = f'Sat {sat_id[-1] if len(sat_id) > 10 else sat_id} (Hogging)' if not hogging_labeled else ''
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
        
        ax.set_title(f'Test: {strategy} - {policy} (All Active Satellites with Buffer States)', fontsize=14, fontweight='bold')
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
        
        # Save test chart with descriptive filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = SCRIPT_DIR / f"test_chart_{timestamp}"
        output_dir.mkdir(exist_ok=True)
        
        # Create filename with time range info if custom time was specified
        if start_time_str and duration_seconds:
            end_time = datetime.strptime(start_time_str, '%H:%M:%S') + timedelta(seconds=duration_seconds)
            time_suffix = f"_{start_time_str.replace(':', '')}-{end_time.strftime('%H%M%S')}"
        elif start_time_str:
            time_suffix = f"_{start_time_str.replace(':', '')}plus"
        else:
            time_suffix = ""
            
        output_file = output_dir / f"test_{strategy}_{policy}{time_suffix}.png"
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
    parser.add_argument('strategy', nargs='?', default='bent-pipe',
                       help='Strategy to analyze (default: bent-pipe)')
    parser.add_argument('policy', nargs='?', default='sticky',
                       help='Policy to analyze (default: sticky)')
    parser.add_argument('start_time', nargs='?', default=None,
                       help='Start time in HH:MM:SS format (default: use first 1000 rows)')
    parser.add_argument('duration', nargs='?', type=int, default=None,
                       help='Duration in seconds (default: no limit if start_time specified)')
    
    return parser.parse_args()

def main():
    args = parse_arguments()
    
    print("Testing single strategy chart generation...")
    print(f"Parameters: strategy={args.strategy}, policy={args.policy}, start_time={args.start_time}, duration={args.duration}")
    
    test_single_strategy(args.strategy, args.policy, args.start_time, args.duration)

if __name__ == "__main__":
    main()
