#!/usr/bin/env python3
"""
Multi-Satellite Idle Time Bar Charts

Creates detailed bar charts showing idle time distribution across satellites.
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

def get_active_satellites():
    """Get satellites that have any downlink activity"""
    policy_dirs = get_policy_dirs()
    all_satellites = set()
    
    for policy, policy_dir in policy_dirs.items():
        tx_rx_file = policy_dir / "meas-downlink-tx-rx.csv"
        if tx_rx_file.exists():
            tx_rx_df = pd.read_csv(tx_rx_file)
            tx_rx_df = tx_rx_df.iloc[:, :2]
            tx_rx_df.columns = ["timestamp", "satellite"]
            
            # Get unique satellites (excluding None/NaN)
            satellites = tx_rx_df["satellite"].dropna()
            satellites = satellites[satellites != "None"]
            all_satellites.update(satellites.unique())
    
    return sorted(list(all_satellites))

def calculate_idle_time_for_policy(policy_dir, satellites):
    """Calculate idle time for a specific policy"""
    print(f"    Calculating idle time for {policy_dir.name}...")
    
    # Load tx-rx data
    tx_rx_file = policy_dir / "meas-downlink-tx-rx.csv"
    if not tx_rx_file.exists():
        print(f"    No tx-rx file found for {policy_dir.name}")
        return {}
    
    tx_rx_df = pd.read_csv(tx_rx_file)
    tx_rx_df = tx_rx_df.iloc[:, :2]
    tx_rx_df.columns = ["timestamp", "satellite"]
    tx_rx_df["timestamp"] = pd.to_datetime(tx_rx_df["timestamp"])
    
    idle_times = {}
    
    for satellite in satellites:
        # Get timesteps when this satellite is connected
        connected_times = tx_rx_df[tx_rx_df["satellite"] == satellite]["timestamp"].tolist()
        
        if not connected_times:
            idle_times[satellite] = 0
            continue
        
        # Load buffer data for this satellite
        # Convert satellite ID format: 60518000-0 -> 0060518000 for buffer file lookup
        if satellite.endswith("-0"):
            # Extract the base number and ensure proper formatting
            sat_base = satellite[:-2]  # Remove "-0" -> 60518000
            # The buffer files have format: meas-MB-buffered-sat-0060518000.csv
            # Need to pad to 10 digits with leading zeros
            sat_id = sat_base.zfill(10)  # 60518000 -> 0060518000
        else:
            sat_id = satellite.zfill(10)
        
        buffer_file = policy_dir / f"meas-MB-buffered-sat-{sat_id}.csv"
        
        if not buffer_file.exists():
            idle_times[satellite] = 0
            continue
        
        buffer_df = pd.read_csv(buffer_file)
        buffer_df = buffer_df.iloc[:, :2]
        buffer_df.columns = ["timestamp", "buffer_mb"]
        buffer_df["timestamp"] = pd.to_datetime(buffer_df["timestamp"])
        buffer_df["buffer_mb"] = pd.to_numeric(buffer_df["buffer_mb"], errors='coerce')
        
        # Count idle timesteps: connected AND buffer = 0
        idle_count = 0
        
        for conn_time in connected_times:
            # Find buffer level at this timestamp
            buffer_at_time = buffer_df[buffer_df["timestamp"] == conn_time]["buffer_mb"]
            
            if len(buffer_at_time) > 0 and buffer_at_time.iloc[0] == 0.0:
                idle_count += 1
        
        idle_times[satellite] = idle_count
    
    return idle_times

def analyze_idle_times():
    """Analyze idle times for all policies"""
    print("Analyzing downlink idle times...")
    
    policy_dirs = get_policy_dirs()
    if not policy_dirs:
        print("No policy directories found!")
        return None
    
    # Get all active satellites
    satellites = get_active_satellites()
    print(f"Found {len(satellites)} active satellites")
    
    results = {}
    
    for policy, policy_dir in policy_dirs.items():
        print(f"  Processing {policy} policy...")
        idle_times = calculate_idle_time_for_policy(policy_dir, satellites)
        results[policy] = idle_times
    
    return results, satellites

def create_idle_time_bars(results, satellites, config):
    """Create detailed idle time bar charts"""
    if not results:
        print("No results to plot!")
        return
    
    # Create output directory with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = SCRIPT_DIR / f"constellation_analysis_{timestamp}"
    output_dir.mkdir(exist_ok=True)
    
    # Set up the plotting style
    plt.style.use('default')
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']
    
    # Get top satellites by total idle time across all policies
    sat_totals = {}
    for satellite in satellites:
        total = sum(results[policy].get(satellite, 0) for policy in POLICIES)
        sat_totals[satellite] = total
    
    top_satellites = sorted(sat_totals.items(), key=lambda x: x[1], reverse=True)[:TOP_N]
    
    if not top_satellites:
        print("No satellites with idle time found!")
        return output_dir
    
    # Create grouped bar chart
    fig, ax = plt.subplots(figsize=(14, 8))
    
    satellite_names = [f"Sat-{sat[0].split('60518')[1][:3] if '60518' in sat[0] else sat[0][-3:]}" for sat in top_satellites]
    x = np.arange(len(satellite_names))
    width = 0.2  # Width of bars
    
    # Create bars for each policy
    for i, policy in enumerate(POLICIES):
        if policy in results:
            values = [results[policy].get(sat[0], 0) for sat in top_satellites]
            offset = (i - len(POLICIES)/2 + 0.5) * width
            bars = ax.bar(x + offset, values, width, label=policy.capitalize(), 
                         color=colors[i % len(colors)], alpha=0.8)
            
            # Add value labels on bars if value > 0
            for bar, value in zip(bars, values):
                if value > 0:
                    height = bar.get_height()
                    ax.text(bar.get_x() + bar.get_width()/2., height + max(values)*0.01,
                           f'{int(value)}', ha='center', va='bottom', fontsize=8)
    
    ax.set_xlabel('Satellite', fontsize=12)
    ax.set_ylabel('Idle Timesteps', fontsize=12)
    ax.set_title('Downlink Idle Time Distribution by Satellite\n(Top 15 Satellites by Total Idle Time)', 
                fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(satellite_names, rotation=45, ha='right')
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3, axis='y')
    
    plt.tight_layout()
    
    # Save grouped bar chart
    bar_chart_path = output_dir / "satellite_idle_bars.png"
    plt.savefig(bar_chart_path, dpi=300, bbox_inches='tight')
    print(f"Saved satellite idle time bar chart: {bar_chart_path}")
    plt.close()
    
    # Also create a summary statistics table
    print("\nIdle Time Summary:")
    print("=================")
    
    for policy in POLICIES:
        if policy in results:
            total_idle = sum(results[policy].values())
            num_idle_sats = sum(1 for v in results[policy].values() if v > 0)
            max_idle = max(results[policy].values()) if results[policy].values() else 0
            
            timestep_duration = config.get('frame_spacing', 1.0)
            total_seconds = total_idle * timestep_duration
            
            print(f"{policy.capitalize()}:")
            print(f"  Total idle time: {total_idle} timesteps ({total_seconds:.1f} seconds)")
            print(f"  Satellites with idle time: {num_idle_sats}")
            print(f"  Maximum idle time per satellite: {max_idle} timesteps")
            print()
    
    return output_dir

def main():
    """Main execution function"""
    print("=== Multi-Satellite Downlink Idle Time Bar Charts ===")
    
    # Read configuration
    config = read_config()
    print(f"Configuration: {config}")
    
    # Analyze idle times
    results, satellites = analyze_idle_times()
    
    if results:
        # Create bar charts
        output_dir = create_idle_time_bars(results, satellites, config)
        print(f"\nBar chart analysis complete! Charts saved to: {output_dir}")
    else:
        print("No results generated!")

if __name__ == "__main__":
    main()
