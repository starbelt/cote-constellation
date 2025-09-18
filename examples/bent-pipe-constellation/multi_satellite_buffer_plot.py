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

# Configuration - use absolute paths
SCRIPT_DIR = Path(__file__).parent.absolute()
LOGS_DIR = SCRIPT_DIR / "logs"
POLICIES = ["sticky", "fifo", "roundrobin", "random"]
TOP_N = 15

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

def get_policy_dirs():
    """Get policy directories"""
    dirs = {}
    for policy in POLICIES:
        policy_dir = LOGS_DIR / policy
        if policy_dir.exists():
            dirs[policy] = policy_dir
    return dirs

def get_top_satellites():
    """Get satellites with most downlink activity based on ACTUAL buffer changes, not just tx-rx logs"""
    policy_dirs = get_policy_dirs()
    all_totals = {}
    
    for policy, policy_dir in policy_dirs.items():
        print(f"  Processing {policy} policy...")
        
        # Check buffer files for actual data downloaded (buffer decreases)
        # Skip the inflated throughput calculation that was giving wrong totals
        for sat_num in range(50):
            sat_id = f"60518{sat_num:03d}-0"
            buffer_file = policy_dir / f"meas-MB-buffered-sat-00{sat_id.replace('-0', '')}.csv"
            
            if buffer_file.exists():
                try:
                    buffer_df = pd.read_csv(buffer_file)
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

def get_global_time_reference():
    """Get global minimum timestamp across all policies for consistent time reference"""
    policy_dirs = get_policy_dirs()
    min_timestamp = None
    
    for policy_dir in policy_dirs.values():
        tx_rx_file = policy_dir / "meas-downlink-tx-rx.csv"
        if not tx_rx_file.exists():
            continue
            
        df = pd.read_csv(tx_rx_file)
        df = df.iloc[:, :2]
        df.columns = ["timestamp", "satellite"]
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        
        file_min = df["timestamp"].min()
        if min_timestamp is None or file_min < min_timestamp:
            min_timestamp = file_min
    
    return min_timestamp

def load_buffer_data(policy, satellite_id):
    """Load buffer data for satellite"""
    sat_num = satellite_id.split("-")[0] if "-" in satellite_id else satellite_id
    policy_dirs = get_policy_dirs()
    
    if policy not in policy_dirs:
        return None
        
    buffer_file = policy_dirs[policy] / f"meas-MB-buffered-sat-{int(sat_num):010d}.csv"
    if not buffer_file.exists():
        return None
        
    df = pd.read_csv(buffer_file)
    # Keep only first 2 columns
    df = df.iloc[:, :2]
    df.columns = ["timestamp", "buffer_mb"]
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    
    # Use global time reference for consistent hours across all policies
    global_min_time = get_global_time_reference()
    df["hours"] = (df["timestamp"] - global_min_time).dt.total_seconds() / 3600
    df["buffer_mb"] = pd.to_numeric(df["buffer_mb"], errors='coerce')
    
    return df

def get_orbital_passes():
    """Get orbital pass times using global time reference"""
    policy_dirs = get_policy_dirs()
    global_min_time = get_global_time_reference()
    
    for policy_dir in policy_dirs.values():
        tx_rx_file = policy_dir / "meas-downlink-tx-rx.csv"
        if not tx_rx_file.exists():
            continue
            
        df = pd.read_csv(tx_rx_file)
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

def create_plot(output_dir=None):
    """Create buffer comparison plot"""
    config = read_config()
    top_satellites, all_totals = get_top_satellites()
    passes = get_orbital_passes()
    
    if not top_satellites:
        print("No satellite data found!")
        return
    
    fig, axes = plt.subplots(2, 2, figsize=(28, 24))  # Increased size for 50-satellite legend
    
    # Create enhanced title
    title_lines = ["Satellite Constellation Buffer Analysis"]
    
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
            
            buffer_df = load_buffer_data(policy, sat_id)
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
    
    # Save plot - use provided output directory or create timestamped one
    if output_dir is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = SCRIPT_DIR / f"buffer_analysis_{timestamp}"
        output_dir.mkdir(exist_ok=True)
        
        # Create log archive only if we're creating our own directory
        create_log_archive(output_dir)
        print(f"Analysis complete! Generated plot with {len(passes)} orbital passes -> {output_dir}/buffer_comparison.png")
    else:
        # Just save the plot when called from combined analysis
        pass
    
    plt.tight_layout()
    plt.savefig(output_dir / "buffer_comparison.png", dpi=300, bbox_inches='tight')
    plt.close()
    
    if output_dir.parent == SCRIPT_DIR:  # Only print if we created our own directory
        print(f"Analysis complete! Generated plot with {len(passes)} orbital passes -> {output_dir}/buffer_comparison.png")

def create_log_archive(output_dir):
    """Create a zip archive of all simulation logs"""
    archive_path = output_dir / "simulation_logs.zip"
    
    with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for policy in POLICIES:
            policy_dir = LOGS_DIR / policy
            if policy_dir.exists():
                for log_file in policy_dir.glob("*.csv"):
                    # Add file to zip with policy folder structure
                    arcname = f"{policy}/{log_file.name}"
                    zipf.write(log_file, arcname)
    
    print(f"Created log archive: {archive_path}")
    return archive_path

def main():
    """Main function"""
    print("Multi-Satellite Buffer Analysis")
    
    policy_dirs = get_policy_dirs()
    if not policy_dirs:
        print("No simulation logs found!")
        print("Please run simulations first using the scripts in the scripts/ directory.")
        return
    
    create_plot()  # Use default behavior when run standalone

if __name__ == "__main__":
    main()
