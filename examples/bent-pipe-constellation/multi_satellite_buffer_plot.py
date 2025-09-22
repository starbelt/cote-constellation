#!/usr/bin/env python3
"""
Multi-Satellite Buffer Analysis

Simple buffer level comparison across scheduling policies.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from datetime import datetime
import zipfile
import glob

# Configuration - use absolute paths
SCRIPT_DIR = Path(__file__).parent.absolute()
LOGS_DIR = SCRIPT_DIR / "logs"
POLICIES = ["sticky", "fifo", "roundrobin", "random"]
STRATEGIES = ["close-spaced", "close-orbit-spaced", "frame-spaced", "orbit-spaced"]
TOP_N = 15

def extract_constellation_data():
    """Extract data from constellation_analysis folders"""
    constellation_folders = []
    
    # Look for constellation_analysis folders in the current directory
    pattern = str(SCRIPT_DIR / "constellation_analysis_*")
    for folder_path in glob.glob(pattern):
        folder = Path(folder_path)
        if folder.is_dir():
            constellation_folders.append(folder)
    
    if not constellation_folders:
        print("No constellation_analysis folders found!")
        return None
    
    # Use the most recent constellation analysis folder
    latest_folder = max(constellation_folders, key=lambda x: x.stat().st_mtime)
    print(f"Using constellation analysis folder: {latest_folder.name}")
    
    return latest_folder

def read_config():
    """Read simulation configuration"""
    config = {}
    
    # Sensor config - use absolute path
    sensor_file = SCRIPT_DIR / "configuration/sensor.dat"
    if sensor_file.exists():
        with open(sensor_file, 'r') as f:
            lines = f.readlines()
            if len(lines) >= 2:
                header = lines[0].strip().split(',')
                values = lines[1].strip().split(',')
                for i, key in enumerate(header):
                    if i < len(values) and key == 'bits-per-sense':
                        config['mb_per_sense'] = int(values[i]) / (8 * 1024 * 1024)
    
    # Constellation config
    constellation_file = SCRIPT_DIR / "configuration/constellation.dat"
    if constellation_file.exists():
        with open(constellation_file, 'r') as f:
            lines = f.readlines()
            if len(lines) >= 2:
                header = lines[0].strip().split(',')
                values = lines[1].strip().split(',')
                for i, key in enumerate(header):
                    if i < len(values):
                        if key == 'count':
                            config['satellite_count'] = int(values[i])
                        elif key == 'second':
                            # Frame spacing in seconds
                            config['frame_spacing'] = float(values[i]) + float(values[i+1]) / 1e9 if i+1 < len(values) else float(values[i])
    
    return config

def get_policy_dirs(strategy_folder):
    """Get policy directories from strategy simulation_logs.zip"""
    simulation_logs_zip = strategy_folder / "simulation_logs.zip"
    
    if not simulation_logs_zip.exists():
        return {}
    
    dirs = {}
    with zipfile.ZipFile(simulation_logs_zip, 'r') as zipf:
        # Check which policies have data in the zip
        for policy in POLICIES:
            policy_files = [name for name in zipf.namelist() if name.startswith(f"{policy}/")]
            if policy_files:
                dirs[policy] = policy  # Store policy name, we'll extract from zip
    
    return dirs

def get_top_satellites(strategy_folder):
    """Get satellites with most downlink activity from strategy folder"""
    simulation_logs_zip = strategy_folder / "simulation_logs.zip"
    
    if not simulation_logs_zip.exists():
        print(f"No simulation_logs.zip found in {strategy_folder}")
        return [], {}
    
    policy_dirs = get_policy_dirs(strategy_folder)
    all_totals = {}
    
    with zipfile.ZipFile(simulation_logs_zip, 'r') as zipf:
        for policy in policy_dirs.keys():
            print(f"  Processing {policy} policy...")
            
            # Check buffer files for actual data downloaded (buffer decreases)
            for sat_num in range(50):
                sat_id = f"60518{sat_num:03d}-0"
                buffer_file_path = f"{policy}/meas-MB-buffered-sat-00{sat_id.replace('-0', '')}.csv"
                
                if buffer_file_path in zipf.namelist():
                    try:
                        with zipf.open(buffer_file_path) as file:
                            buffer_df = pd.read_csv(file)
                            if len(buffer_df) > 1:
                                buffer_col = f"MB-buffered-sat-00{sat_id.replace('-0', '')}"
                                if buffer_col in buffer_df.columns:
                                    # Calculate total data downloaded by looking at buffer decrease + tx-rx events
                                    buffer_df['prev_value'] = buffer_df[buffer_col].shift(1)
                                    buffer_df['decrease'] = buffer_df['prev_value'] - buffer_df[buffer_col]
                                    
                                    # Sum all buffer decreases (data flowing out) - more accurate than arbitrary threshold
                                    total_downloaded = buffer_df[buffer_df['decrease'] > 0]['decrease'].sum()
                                    
                                    if total_downloaded > 0:
                                        if sat_id not in all_totals:
                                            all_totals[sat_id] = {}
                                        if policy not in all_totals[sat_id]:
                                            all_totals[sat_id][policy] = 0
                                        # Use actual buffer decreases as total downloaded
                                        all_totals[sat_id][policy] = total_downloaded
                    except Exception as e:
                        pass  # Skip files that can't be read
    
    # Get top satellites by max usage
    sat_max = {sat: max(policies.values()) for sat, policies in all_totals.items()}
    top_sats = sorted(sat_max.items(), key=lambda x: x[1], reverse=True)[:TOP_N]
    
    return [sat for sat, _ in top_sats], all_totals

def get_global_time_reference(strategy_folder):
    """Get global minimum timestamp across all policies for consistent time reference"""
    simulation_logs_zip = strategy_folder / "simulation_logs.zip"
    
    if not simulation_logs_zip.exists():
        return None
    
    policy_dirs = get_policy_dirs(strategy_folder)
    min_timestamp = None
    
    with zipfile.ZipFile(simulation_logs_zip, 'r') as zipf:
        for policy in policy_dirs.keys():
            tx_rx_file_path = f"{policy}/meas-downlink-tx-rx.csv"
            if tx_rx_file_path not in zipf.namelist():
                continue
                
            with zipf.open(tx_rx_file_path) as file:
                df = pd.read_csv(file)
                df = df.iloc[:, :2]
                df.columns = ["timestamp", "satellite"]
                df["timestamp"] = pd.to_datetime(df["timestamp"])
                
                file_min = df["timestamp"].min()
                if min_timestamp is None or file_min < min_timestamp:
                    min_timestamp = file_min
    
    return min_timestamp

def load_buffer_data(strategy_folder, policy, satellite_id):
    """Load buffer data for satellite from strategy folder"""
    simulation_logs_zip = strategy_folder / "simulation_logs.zip"
    
    if not simulation_logs_zip.exists():
        return None
    
    sat_num = satellite_id.split("-")[0] if "-" in satellite_id else satellite_id
    policy_dirs = get_policy_dirs(strategy_folder)
    
    if policy not in policy_dirs:
        return None
    
    buffer_file_path = f"{policy}/meas-MB-buffered-sat-{int(sat_num):010d}.csv"
    
    with zipfile.ZipFile(simulation_logs_zip, 'r') as zipf:
        if buffer_file_path not in zipf.namelist():
            return None
            
        with zipf.open(buffer_file_path) as file:
            df = pd.read_csv(file)
            # Keep only first 2 columns
            df = df.iloc[:, :2]
            df.columns = ["timestamp", "buffer_mb"]
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            
            # Use global time reference for consistent hours across all policies
            global_min_time = get_global_time_reference(strategy_folder)
            df["hours"] = (df["timestamp"] - global_min_time).dt.total_seconds() / 3600
            df["buffer_mb"] = pd.to_numeric(df["buffer_mb"], errors='coerce')
            
            return df

def get_orbital_passes(strategy_folder):
    """Get orbital pass times using global time reference"""
    simulation_logs_zip = strategy_folder / "simulation_logs.zip"
    
    if not simulation_logs_zip.exists():
        return []
    
    policy_dirs = get_policy_dirs(strategy_folder)
    global_min_time = get_global_time_reference(strategy_folder)
    
    with zipfile.ZipFile(simulation_logs_zip, 'r') as zipf:
        for policy in policy_dirs.keys():
            tx_rx_file_path = f"{policy}/meas-downlink-tx-rx.csv"
            if tx_rx_file_path not in zipf.namelist():
                continue
                
            with zipf.open(tx_rx_file_path) as file:
                df = pd.read_csv(file)
                # Keep only first 2 columns
                df = df.iloc[:, :2]
                df.columns = ["timestamp", "satellite"]
                df["timestamp"] = pd.to_datetime(df["timestamp"])
                
                # Use global time reference for consistent hours across all policies
                df["hours"] = (df["timestamp"] - global_min_time).dt.total_seconds() / 3600
                
                active_times = sorted(df[df["satellite"].notnull()]["hours"].tolist())
                if not active_times:
                    continue
                    
                # Group into passes
                passes = []
                start, last = None, None
                for time in active_times:
                    if last is None or (time - last) > 0.5:  # 30min gap
                        if start is not None:
                            passes.append((start, last))
                        start = time
                    last = time
                if start is not None:
                    passes.append((start, last))
                    
                return passes
    
    return []

def create_plot(strategy_folder, strategy_name, constellation_analysis_folder):
    """Create buffer comparison plot for a specific strategy"""
    config = read_config()
    top_satellites, all_totals = get_top_satellites(strategy_folder)
    passes = get_orbital_passes(strategy_folder)
    
    if not top_satellites:
        print(f"No satellite data found for {strategy_name}!")
        return
    
    fig, axes = plt.subplots(2, 2, figsize=(28, 24))  # Increased size for 50-satellite legend
    
    # Create enhanced title
    title_lines = [f"Satellite Constellation Buffer Analysis - {strategy_name.title()} Strategy"]
    
    # Add constellation parameters
    sat_count = config.get('satellite_count', 'Unknown')
    frame_spacing = config.get('frame_spacing')
    mb_per_sense = config.get('mb_per_sense')
    
    if sat_count != 'Unknown' and frame_spacing and mb_per_sense:
        title_lines.append(f"{sat_count} Satellites | Frame Rate: 1 image/{frame_spacing:.1f}s | Image Size: {mb_per_sense:.2f} MB")
    elif mb_per_sense:
        title_lines.append(f"Image Size: {mb_per_sense:.2f} MB")
    
    title_lines.append(f"Buffer Levels Over Time (All Active Satellites Per Policy)")
    
    title = '\n'.join(title_lines)
    fig.suptitle(title, fontsize=16, fontweight='bold')
    
    for i, policy in enumerate(POLICIES):
        ax = axes[i // 2, i % 2]
        
        # FIX: Calculate total from ALL satellites, not just top 15
        total_data = 0
        for sat_id in all_totals:
            sat_total = all_totals.get(sat_id, {}).get(policy, 0)
            total_data += sat_total
        
        legend_data = []
        
        # Generate all 50 satellite IDs in the format that matches the data ('60518000-0', etc.)
        all_50_satellites = [f"60518{i:03d}-0" for i in range(50)]
        
        # Use colors that cycle through the palette for all 50 satellites
        policy_colors = plt.cm.tab20(np.linspace(0, 1, 20))
        extra_colors = plt.cm.Set3(np.linspace(0, 1, 20))
        extended_colors = plt.cm.Dark2(np.linspace(0, 1, 10))
        all_colors = list(policy_colors) + list(extra_colors) + list(extended_colors)
        
        for j, sat_id in enumerate(all_50_satellites):
            sat_num = sat_id.split("-")[0]  # Extract the number part (60518000, 60518001, etc.)
            sat_total = all_totals.get(sat_id, {}).get(policy, 0)
            color = all_colors[j % len(all_colors)]
            
            buffer_df = load_buffer_data(strategy_folder, policy, sat_id)
            if buffer_df is None or sat_total == 0:
                # No buffer data file found or no downlink data - use greyed line at zero
                line = ax.axhline(0, color='lightgray', alpha=0.3, linestyle='--', linewidth=0.5)
                legend_data.append((sat_total, line, f'{sat_id} (0MB)', True))  # True = greyed
            else:
                # Buffer data exists and has downlink data - use normal colored line
                line = ax.plot(buffer_df['hours'], buffer_df['buffer_mb'], 
                       color=color, linewidth=1.5, alpha=0.8, linestyle='solid')[0]
                legend_data.append((sat_total, line, f'{sat_id} ({sat_total:.0f}MB)', False))  # False = normal
        
        # Add orbital passes
        for start, end in passes:
            ax.axvspan(start, end, alpha=0.1, color='green')
        
        # Sort legend: active satellites first (by data amount, highest first), then greyed satellites by number
        active_legends = [(data, line, label) for data, line, label, is_grey in legend_data if not is_grey]
        greyed_legends = [(data, line, label) for data, line, label, is_grey in legend_data if is_grey]
        
        # Sort active by data amount (descending), greyed by satellite number (ascending)
        active_legends.sort(key=lambda x: x[0], reverse=True)
        greyed_legends.sort(key=lambda x: x[2])  # Sort by label (contains sat number)
        
        # Combine: active satellites first, then greyed satellites
        sorted_legends = active_legends + greyed_legends
        
        handles = [item[1] for item in sorted_legends]
        labels = [item[2] for item in sorted_legends]
        
        ax.set_xlabel('Time (hours)')
        ax.set_ylabel('Buffer (MB)')
        ax.set_title(f'{policy.upper()} Scheduling\nTotal Downloaded: {total_data:.0f} MB', fontweight='bold')
        ax.grid(True, alpha=0.3)
        ax.legend(handles, labels, bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=7)
    
    # Save plot in the constellation analysis folder with strategy-specific naming
    output_filename = f"buffer_plot_{strategy_name}_strategy.png"
    output_path = constellation_analysis_folder / output_filename
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"Generated {strategy_name} buffer plot with {len(passes)} orbital passes -> {output_path}")
    return output_path

def main():
    """Main function"""
    print("Multi-Satellite Buffer Analysis")
    
    # Extract constellation analysis data
    constellation_analysis_folder = extract_constellation_data()
    if not constellation_analysis_folder:
        print("No constellation analysis data found!")
        print("Please run constellation analysis first.")
        return
    
    print(f"Processing constellation analysis folder: {constellation_analysis_folder.name}")
    
    # Process each strategy
    generated_plots = []
    for strategy in STRATEGIES:
        strategy_folder = constellation_analysis_folder / strategy
        if strategy_folder.exists():
            print(f"\nProcessing {strategy} strategy...")
            try:
                output_path = create_plot(strategy_folder, strategy, constellation_analysis_folder)
                if output_path:
                    generated_plots.append(output_path)
            except Exception as e:
                print(f"Error processing {strategy} strategy: {e}")
        else:
            print(f"Strategy folder not found: {strategy}")
    
    if generated_plots:
        print(f"\nBuffer analysis complete! Generated {len(generated_plots)} plots:")
        for plot_path in generated_plots:
            print(f"  {plot_path}")
    else:
        print("No plots were generated.")

if __name__ == "__main__":
    main()
