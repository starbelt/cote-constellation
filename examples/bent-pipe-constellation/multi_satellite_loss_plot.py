#!/usr/bin/env python3
"""
Multi-Satellite Data Loss Analysis

Simple cumulative data loss comparison across scheduling policies.
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
                    if i < len(values):
                        if key == 'bits-per-sense':
                            config['mb_per_sense'] = int(values[i]) / (8 * 1024 * 1024)
                        elif key == 'max-buffer-mb':
                            config['max_buffer_mb'] = float(values[i])
    
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

def get_satellites_with_overflow():
    """Get satellites that have overflow data across all policies"""
    policy_dirs = get_policy_dirs()
    all_overflow_sats = set()
    
    for policy, policy_dir in policy_dirs.items():
        # Find all buffer overflow files
        overflow_files = list(policy_dir.glob("meas-buffer-overflow-sat-*.csv"))
        for overflow_file in overflow_files:
            # Extract satellite ID from filename
            sat_id = overflow_file.stem.replace("meas-buffer-overflow-sat-", "")
            all_overflow_sats.add(sat_id)
    
    return sorted(list(all_overflow_sats))

def get_top_satellites_by_loss():
    """Get top satellites by total data loss across all policies"""
    policy_dirs = get_policy_dirs()
    all_totals = {}
    
    print("Scanning overflow files...")
    for policy, policy_dir in policy_dirs.items():
        overflow_files = list(policy_dir.glob("meas-buffer-overflow-sat-*.csv"))
        print(f"  {policy}: {len(overflow_files)} overflow files")
        
        for overflow_file in overflow_files:
            sat_id = overflow_file.stem.replace("meas-buffer-overflow-sat-", "")
            
            try:
                df = pd.read_csv(overflow_file)
                if len(df) > 0:
                    # Get the final (maximum) cumulative loss - just read last line
                    df = df.iloc[:, :2]  # Keep only first 2 columns
                    df.columns = ["timestamp", "loss_mb"]
                    df["loss_mb"] = pd.to_numeric(df["loss_mb"], errors='coerce')
                    max_loss = df["loss_mb"].iloc[-1]  # Last value is the maximum cumulative
                    
                    if pd.notna(max_loss) and max_loss > 0:
                        if sat_id not in all_totals:
                            all_totals[sat_id] = {}
                        all_totals[sat_id][policy] = max_loss
            except Exception as e:
                print(f"Warning: Could not read {overflow_file}: {e}")
                continue
    
    # Get top satellites by max loss
    sat_max = {sat: max(policies.values()) for sat, policies in all_totals.items()}
    top_sats = sorted(sat_max.items(), key=lambda x: x[1], reverse=True)[:TOP_N]
    
    print(f"Found {len(all_totals)} satellites with data loss")
    return [sat for sat, _ in top_sats], all_totals

# Cache for global time reference to avoid repeated expensive calculations
_global_time_cache = None

def get_global_time_reference():
    """Get global minimum timestamp across all policies for consistent time reference"""
    global _global_time_cache
    if _global_time_cache is not None:
        return _global_time_cache
    
    policy_dirs = get_policy_dirs()
    min_timestamp = None
    
    # Check ALL possible timestamp sources to find the absolute earliest time
    for policy_dir in policy_dirs.values():
        # Check tx-rx files first (these typically start earliest)
        tx_rx_file = policy_dir / "meas-downlink-tx-rx.csv"
        if tx_rx_file.exists():
            try:
                df = pd.read_csv(tx_rx_file)
                if len(df) > 0:
                    df = df.iloc[:, :2]
                    df.columns = ["timestamp", "satellite"]
                    df["timestamp"] = pd.to_datetime(df["timestamp"])
                    file_min = df["timestamp"].min()
                    if min_timestamp is None or file_min < min_timestamp:
                        min_timestamp = file_min
            except:
                continue
        
        # Also check buffer files for completeness
        buffer_files = list(policy_dir.glob("meas-MB-buffered-sat-*.csv"))
        for buffer_file in buffer_files[:5]:  # Check first 5 buffer files
            try:
                df = pd.read_csv(buffer_file)
                if len(df) > 0:
                    df = df.iloc[:, :2]
                    df.columns = ["timestamp", "buffer_mb"]
                    df["timestamp"] = pd.to_datetime(df["timestamp"])
                    file_min = df["timestamp"].min()
                    if min_timestamp is None or file_min < min_timestamp:
                        min_timestamp = file_min
                    break  # Just check one buffer file per policy
            except:
                continue
        
        # Check overflow files last (these typically start later)
        overflow_files = list(policy_dir.glob("meas-buffer-overflow-sat-*.csv"))
        for overflow_file in overflow_files[:5]:  # Check first 5 overflow files
            try:
                df = pd.read_csv(overflow_file)
                if len(df) > 0:
                    df = df.iloc[:, :2]
                    df.columns = ["timestamp", "loss_mb"]
                    df["timestamp"] = pd.to_datetime(df["timestamp"])
                    file_min = df["timestamp"].min()
                    if min_timestamp is None or file_min < min_timestamp:
                        min_timestamp = file_min
                    break  # Just check one overflow file per policy
            except:
                continue
    
    _global_time_cache = min_timestamp
    return min_timestamp

def load_loss_data(policy, satellite_id):
    """Load cumulative loss data for satellite"""
    policy_dirs = get_policy_dirs()
    
    if policy not in policy_dirs:
        return None
        
    overflow_file = policy_dirs[policy] / f"meas-buffer-overflow-sat-{satellite_id}.csv"
    if not overflow_file.exists():
        return None
        
    try:
        df = pd.read_csv(overflow_file)
        if len(df) == 0:
            return None
            
        # Keep only first 2 columns
        df = df.iloc[:, :2]
        df.columns = ["timestamp", "loss_mb"]
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        
        # Use global time reference for consistent hours across all policies
        global_min_time = get_global_time_reference()
        df["hours"] = (df["timestamp"] - global_min_time).dt.total_seconds() / 3600
        df["loss_mb"] = pd.to_numeric(df["loss_mb"], errors='coerce')
        
        return df
    except Exception as e:
        print(f"Warning: Could not read {overflow_file}: {e}")
        return None

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

def create_plot():
    """Create data loss comparison plot"""
    print("Starting data loss analysis...")
    config = read_config()
    top_satellites, all_totals = get_top_satellites_by_loss()
    passes = get_orbital_passes()
    
    if not top_satellites:
        print("No data loss found! This means buffer caps are working well or are set too high.")
        print("Consider reducing max-buffer-mb in sensor.dat to see overflow behavior.")
        print("Creating charts anyway - they will show zero losses.")
        # Use a dummy satellite list for the chart structure
        top_satellites = ['00001', '00002', '00003']  # Show a few satellites with zero loss
        all_totals = {}
    
    print(f"Creating plots for {len(top_satellites)} satellites...")
    fig, axes = plt.subplots(2, 2, figsize=(28, 24))  # Increased size for 50-satellite legend
    
    # Create enhanced title
    title_lines = ["Satellite Constellation Data Loss Analysis"]
    
    # Add constellation parameters
    sat_count = config.get('satellite_count', 'Unknown')
    frame_spacing = config.get('frame_spacing')
    mb_per_sense = config.get('mb_per_sense')
    max_buffer_mb = config.get('max_buffer_mb')
    
    if sat_count != 'Unknown' and frame_spacing and mb_per_sense:
        buffer_info = f" | Buffer Cap: {max_buffer_mb:.0f} MB" if max_buffer_mb else ""
        title_lines.append(f"{sat_count} Satellites | Frame Rate: 1 image/{frame_spacing:.1f}s | Image Size: {mb_per_sense:.2f} MB{buffer_info}")
    elif mb_per_sense:
        buffer_info = f" | Buffer Cap: {max_buffer_mb:.0f} MB" if max_buffer_mb else ""
        title_lines.append(f"Image Size: {mb_per_sense:.2f} MB{buffer_info}")
    
    title_lines.append(f"Top {min(TOP_N, len(top_satellites))} Satellites by Cumulative Data Loss")
    
    title = '\n'.join(title_lines)
    fig.suptitle(title, fontsize=16, fontweight='bold')
    
    for i, policy in enumerate(POLICIES):
        print(f"  Processing {policy} policy ({i+1}/{len(POLICIES)})...")
        ax = axes[i // 2, i % 2]
        
        total_loss = 0
        legend_data = []
        
        # Generate all 50 satellite IDs in the format that matches the data ('60518000', etc.)
        all_50_satellites = [f"60518{i:03d}" for i in range(50)]
        
        # Use colors that cycle through the palette for all 50 satellites
        colors = plt.cm.tab20(np.linspace(0, 1, 20))
        extra_colors = plt.cm.Set3(np.linspace(0, 1, 20))
        extended_colors = plt.cm.Dark2(np.linspace(0, 1, 10))
        all_colors = list(colors) + list(extra_colors) + list(extended_colors)
        
        for j, sat_id in enumerate(all_50_satellites):
            sat_num = sat_id  # sat_id is already just the number (60518000, 60518001, etc.)
            sat_total = all_totals.get(sat_id, {}).get(policy, 0)
            total_loss += sat_total
            color = all_colors[j % len(all_colors)]
            
            loss_df = load_loss_data(policy, sat_id)
            if loss_df is None or len(loss_df) == 0 or sat_total == 0:
                # No loss data or no actual loss - use greyed line at zero
                line = ax.axhline(0, color='lightgray', alpha=0.3, linestyle='--', linewidth=0.5)
                legend_data.append((sat_total, line, f'{sat_id} (0MB)', True))  # True = greyed
            else:
                # Loss data exists - use normal colored line
                line = ax.plot(loss_df['hours'], loss_df['loss_mb'], 
                       color=color, linewidth=2, alpha=0.8, linestyle='solid')[0]
                legend_data.append((sat_total, line, f'{sat_id} ({sat_total:.0f}MB)', False))  # False = normal
        
        # Add orbital passes
        for start, end in passes:
            ax.axvspan(start, end, alpha=0.1, color='green')
        
        # Sort legend: active satellites first (by loss amount, highest first), then greyed satellites by number
        active_legends = [(data, line, label) for data, line, label, is_grey in legend_data if not is_grey]
        greyed_legends = [(data, line, label) for data, line, label, is_grey in legend_data if is_grey]
        
        # Sort active by loss amount (descending), greyed by satellite number (ascending)
        active_legends.sort(key=lambda x: x[0], reverse=True)
        greyed_legends.sort(key=lambda x: x[2])  # Sort by label (contains sat number)
        
        # Combine: active satellites first, then greyed satellites
        sorted_legends = active_legends + greyed_legends
        
        handles = [item[1] for item in sorted_legends]
        labels = [item[2] for item in sorted_legends]
        
        ax.set_xlabel('Time (hours)')
        ax.set_ylabel('Cumulative Data Loss (MB)')
        ax.set_title(f'{policy.upper()}\nTotal Loss: {total_loss:.0f} MB')
        ax.grid(True, alpha=0.3)
        ax.legend(handles, labels, bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=7)
        
        # Set y-axis to start at 0
        ax.set_ylim(bottom=0)
    
    # Save plot - use absolute paths for output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = SCRIPT_DIR / f"loss_analysis_{timestamp}"
    output_dir.mkdir(exist_ok=True)
    
    plt.tight_layout()
    plt.savefig(output_dir / "loss_comparison.png", dpi=300, bbox_inches='tight')
    plt.close()
    
    # Create log archive
    create_log_archive(output_dir)
    
    print(f"Analysis complete! Generated plot with {len(passes)} orbital passes -> {output_dir}/loss_comparison.png")
    print(f"Found {len(top_satellites)} satellites with data loss across {len(POLICIES)} policies")

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
    print("Multi-Satellite Data Loss Analysis")
    
    policy_dirs = get_policy_dirs()
    if not policy_dirs:
        print("No simulation logs found!")
        print("Please run simulations first using the scripts in the scripts/ directory.")
        return
    
    create_plot()

if __name__ == "__main__":
    main()
