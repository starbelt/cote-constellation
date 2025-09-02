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

# Configuration
LOGS_DIR = Path("logs")
POLICIES = ["greedy", "fifo", "roundrobin", "random"]
TOP_N = 15

def read_config():
    """Read simulation configuration"""
    config = {}
    
    # Sensor config
    sensor_file = Path("configuration/sensor.dat")
    if sensor_file.exists():
        with open(sensor_file, 'r') as f:
            lines = f.readlines()
            if len(lines) >= 2:
                header = lines[0].strip().split(',')
                values = lines[1].strip().split(',')
                for i, key in enumerate(header):
                    if i < len(values) and key == 'bits-per-sense':
                        config['mb_per_sense'] = int(values[i]) / (8 * 1024 * 1024)
    
    return config

def get_policy_dirs():
    """Get policy directories"""
    dirs = {}
    for policy in POLICIES:
        # Look for numbered directories first (latest run)
        max_run = -1
        latest_dir = None
        
        if LOGS_DIR.exists():
            for item in LOGS_DIR.iterdir():
                if item.is_dir() and item.name.startswith(policy):
                    suffix = item.name[len(policy):]
                    if suffix.isdigit():
                        run_num = int(suffix)
                        if run_num > max_run:
                            max_run = run_num
                            latest_dir = item
        
        if latest_dir:
            dirs[policy] = latest_dir
        else:
            # Fallback to basic directory name
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
        
        # Calculate totals per satellite
        for _, row in tx_rx_df.iterrows():
            sat = row["satellite"]
            if sat == "None" or pd.isna(sat):
                continue
                
            mbps_row = mbps_df[mbps_df["timestamp"] == row["timestamp"]]
            if not mbps_row.empty:
                mbps = mbps_row.iloc[0]["mbps"]
                if pd.notna(mbps):
                    data_mb = mbps * 100 / 8  # 100s timestep
                    if sat not in all_totals:
                        all_totals[sat] = {}
                    if policy not in all_totals[sat]:
                        all_totals[sat][policy] = 0
                    all_totals[sat][policy] += data_mb
    
    # Get top satellites by max usage
    sat_max = {sat: max(policies.values()) for sat, policies in all_totals.items()}
    top_sats = sorted(sat_max.items(), key=lambda x: x[1], reverse=True)[:TOP_N]
    
    return [sat for sat, _ in top_sats], all_totals

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
    df["hours"] = (df["timestamp"] - df["timestamp"].min()).dt.total_seconds() / 3600
    df["buffer_mb"] = pd.to_numeric(df["buffer_mb"], errors='coerce')
    
    return df

def get_orbital_passes():
    """Get orbital pass times"""
    policy_dirs = get_policy_dirs()
    
    for policy_dir in policy_dirs.values():
        tx_rx_file = policy_dir / "meas-downlink-tx-rx.csv"
        if not tx_rx_file.exists():
            continue
            
        df = pd.read_csv(tx_rx_file)
        # Keep only first 2 columns
        df = df.iloc[:, :2]
        df.columns = ["timestamp", "satellite"]
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["hours"] = (df["timestamp"] - df["timestamp"].min()).dt.total_seconds() / 3600
        
        active_times = sorted(df[df["satellite"] != "None"]["hours"].tolist())
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
    """Create buffer comparison plot"""
    config = read_config()
    top_satellites, all_totals = get_top_satellites()
    passes = get_orbital_passes()
    
    if not top_satellites:
        print("No satellite data found!")
        return
    
    fig, axes = plt.subplots(2, 2, figsize=(20, 16))
    title = f'Buffer Levels - Top {TOP_N} Satellites'
    if config.get('mb_per_sense'):
        title += f'\nConfig: {config["mb_per_sense"]:.2f} MB/image'
    fig.suptitle(title, fontsize=16, fontweight='bold')
    
    colors = plt.cm.tab20(np.linspace(0, 1, len(top_satellites)))
    
    for i, policy in enumerate(POLICIES):
        ax = axes[i // 2, i % 2]
        
        total_data = 0
        legend_data = []
        
        for j, sat_id in enumerate(top_satellites):
            sat_num = sat_id.split("-")[0] if "-" in sat_id else sat_id
            sat_total = all_totals.get(sat_id, {}).get(policy, 0)
            total_data += sat_total
            
            buffer_df = load_buffer_data(policy, sat_id)
            if buffer_df is None:
                line = ax.axhline(0, color=colors[j], alpha=0.3, linestyle='--')
                legend_data.append((sat_total, line, f'Sat {sat_num} (0MB)'))
            else:
                style = 'solid' if sat_total > 0 else 'dashed'
                alpha = 0.8 if sat_total > 0 else 0.3
                line = ax.plot(buffer_df['hours'], buffer_df['buffer_mb'], 
                       color=colors[j], linewidth=1.5, alpha=alpha, linestyle=style)[0]
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
        ax.set_title(f'{policy.upper()}\nTotal: {total_data:.0f} MB')
        ax.grid(True, alpha=0.3)
        ax.legend(handles, labels, bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=7)
    
    # Save plot
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(f"buffer_analysis_{timestamp}")
    output_dir.mkdir(exist_ok=True)
    
    plt.tight_layout()
    plt.savefig(output_dir / "buffer_comparison.png", dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"Analysis complete! Generated plot with {len(passes)} orbital passes -> {output_dir}/buffer_comparison.png")

def main():
    """Main function"""
    print("Multi-Satellite Buffer Analysis")
    
    policy_dirs = get_policy_dirs()
    if not policy_dirs:
        print("No simulation logs found!")
        return
    
    create_plot()

if __name__ == "__main__":
    main()
