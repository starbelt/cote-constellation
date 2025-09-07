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
POLICIES = ["greedy", "fifo", "roundrobin", "random"]
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
    """Get top satellites by usage across all policies"""
    policy_dirs = get_policy_dirs()
    all_totals = {}
    
    for policy, policy_dir in policy_dirs.items():
        tx_rx_file = policy_dir / "meas-downlink-tx-rx.csv"
        mbps_file = policy_dir / "meas-downlink-Mbps.csv"
        
        if not (tx_rx_file.exists() and mbps_file.exists()):
            continue
            
        tx_rx_df = pd.read_csv(tx_rx_file)
        mbps_df = pd.read_csv(mbps_file)
        
        # Handle CSV structure - keep only the first 2 columns
        tx_rx_df = tx_rx_df.iloc[:, :2]
        mbps_df = mbps_df.iloc[:, :2]
        
        # Standardize columns
        tx_rx_df.columns = ["timestamp", "satellite"]
        mbps_df.columns = ["timestamp", "mbps"]
        
        tx_rx_df["timestamp"] = pd.to_datetime(tx_rx_df["timestamp"])
        mbps_df["timestamp"] = pd.to_datetime(mbps_df["timestamp"])
        mbps_df["mbps"] = pd.to_numeric(mbps_df["mbps"], errors='coerce')
        
        # Calculate totals per satellite - FIX: Use index-based matching instead of timestamp matching
        tx_rx_list = tx_rx_df.to_dict('records')
        mbps_list = mbps_df.to_dict('records')
        
        policy_total = 0
        matches = 0
        
        for i, tx_row in enumerate(tx_rx_list):
            sat = tx_row["satellite"]
            if pd.isna(sat) or sat == "None":
                continue
                
            # Use index-based matching instead of timestamp matching
            if i < len(mbps_list):
                mbps = mbps_list[i]["mbps"]
                if pd.notna(mbps) and mbps > 0:
                    data_mb = mbps * 100 / 8  # 100s timestep
                    policy_total += data_mb
                    matches += 1
                    if sat not in all_totals:
                        all_totals[sat] = {}
                    if policy not in all_totals[sat]:
                        all_totals[sat][policy] = 0
                    all_totals[sat][policy] += data_mb
    
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
    
    fig, axes = plt.subplots(2, 2, figsize=(20, 16))
    
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
        
        # Get all satellites that this policy actually uses (not just global top 15)
        policy_satellites = [sat_id for sat_id in all_totals if all_totals[sat_id].get(policy, 0) > 0]
        # Sort by this policy's usage (highest first)
        policy_satellites.sort(key=lambda sat: all_totals[sat].get(policy, 0), reverse=True)
        
        # Use colors that cycle through the palette
        policy_colors = plt.cm.tab20(np.linspace(0, 1, min(len(policy_satellites), 20)))
        if len(policy_satellites) > 20:
            # Extend colors for more satellites
            extra_colors = plt.cm.Set3(np.linspace(0, 1, len(policy_satellites) - 20))
            policy_colors = list(policy_colors) + list(extra_colors)
        
        for j, sat_id in enumerate(policy_satellites):
            sat_num = sat_id.split("-")[0] if "-" in sat_id else sat_id
            sat_total = all_totals.get(sat_id, {}).get(policy, 0)
            
            buffer_df = load_buffer_data(policy, sat_id)
            if buffer_df is None:
                # No buffer data file found - use dashed line at zero
                color = policy_colors[j % len(policy_colors)]
                line = ax.axhline(0, color=color, alpha=0.3, linestyle='--')
                legend_data.append((sat_total, line, f'Sat {sat_num} (0MB)'))
            else:
                # Buffer data exists - always use solid line, adjust alpha based on data amount
                alpha = 0.8 if sat_total > 0 else 0.4
                color = policy_colors[j % len(policy_colors)]
                line = ax.plot(buffer_df['hours'], buffer_df['buffer_mb'], 
                       color=color, linewidth=1.5, alpha=alpha, linestyle='solid')[0]
                legend_data.append((sat_total, line, f'Sat {sat_num} ({sat_total:.0f}MB)'))
        
        # Add orbital passes
        for start, end in passes:
            ax.axvspan(start, end, alpha=0.1, color='green')
        
        # Sort legend by data amount (highest first)
        legend_data.sort(key=lambda x: x[0], reverse=True)
        handles = [item[1] for item in legend_data]
        labels = [item[2] for item in legend_data]
        
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
