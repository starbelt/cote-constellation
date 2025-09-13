#!/usr/bin/env python3
"""
Multi-Satellite Idle Time Analysis

Analyzes downlink idle time - periods when ground station is connected 
to a satellite but the satellite's buffer is empty (0 MB).
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

def calculate_cumulative_idle_time_for_policy(policy_dir, satellites):
    """Calculate cumulative idle time over time for a specific policy"""
    print(f"    Calculating cumulative idle time for {policy_dir.name}...")
    
    # Load tx-rx data to get the time baseline
    tx_rx_file = policy_dir / "meas-downlink-tx-rx.csv"
    if not tx_rx_file.exists():
        print(f"    No tx-rx file found for {policy_dir.name}")
        return {}
    
    tx_rx_df = pd.read_csv(tx_rx_file)
    tx_rx_df = tx_rx_df.iloc[:, :2]
    tx_rx_df.columns = ["timestamp", "satellite"]
    tx_rx_df["timestamp"] = pd.to_datetime(tx_rx_df["timestamp"])
    
    # Get global time reference
    global_min_time = tx_rx_df["timestamp"].min()
    tx_rx_df["hours"] = (tx_rx_df["timestamp"] - global_min_time).dt.total_seconds() / 3600
    
    cumulative_idle_data = {}
    
    for satellite in satellites:
        # Get timesteps when this satellite is connected
        connected_entries = tx_rx_df[tx_rx_df["satellite"] == satellite]
        
        if connected_entries.empty:
            cumulative_idle_data[satellite] = {"hours": [], "cumulative_idle": []}
            continue
        
        # Load buffer data for this satellite
        # Convert satellite ID format: 60518000-0 -> 0060518000 for buffer file lookup
        if satellite.endswith("-0"):
            sat_base = satellite[:-2]  # Remove "-0" -> 60518000
            sat_id = sat_base.zfill(10)  # 60518000 -> 0060518000
        else:
            sat_id = satellite.zfill(10)
        
        buffer_file = policy_dir / f"meas-MB-buffered-sat-{sat_id}.csv"
        
        if not buffer_file.exists():
            cumulative_idle_data[satellite] = {"hours": [], "cumulative_idle": []}
            continue
        
        buffer_df = pd.read_csv(buffer_file)
        buffer_df = buffer_df.iloc[:, :2]
        buffer_df.columns = ["timestamp", "buffer_mb"]
        buffer_df["timestamp"] = pd.to_datetime(buffer_df["timestamp"])
        buffer_df["buffer_mb"] = pd.to_numeric(buffer_df["buffer_mb"], errors='coerce')
        buffer_df["hours"] = (buffer_df["timestamp"] - global_min_time).dt.total_seconds() / 3600
        
        # Calculate cumulative idle time: count timesteps where connected AND buffer = 0
        hours_list = []
        cumulative_idle_list = []
        cumulative_idle = 0
        
        # Merge connection and buffer data by timestamp
        for _, conn_row in connected_entries.iterrows():
            conn_time = conn_row["timestamp"]
            conn_hours = conn_row["hours"]
            
            # Find buffer level at this timestamp
            buffer_at_time = buffer_df[buffer_df["timestamp"] == conn_time]["buffer_mb"]
            
            if len(buffer_at_time) > 0 and buffer_at_time.iloc[0] == 0.0:
                cumulative_idle += 1
            
            hours_list.append(conn_hours)
            cumulative_idle_list.append(cumulative_idle)
        
        cumulative_idle_data[satellite] = {
            "hours": hours_list,
            "cumulative_idle": cumulative_idle_list
        }
        
        if cumulative_idle > 0:
            print(f"      Satellite {satellite}: {cumulative_idle} total idle timesteps")
    
    return cumulative_idle_data

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
        cumulative_data = calculate_cumulative_idle_time_for_policy(policy_dir, satellites)
        results[policy] = cumulative_data
    
    return results, satellites

def create_idle_time_charts(results, satellites, config):
    """Create idle time comparison charts similar to buffer comparison"""
    if not results:
        print("No results to plot!")
        return
    
    # Calculate final idle time totals per policy for the summary
    policy_totals = {}
    for policy, cumulative_data in results.items():
        total = 0
        for satellite in satellites:
            sat_data = cumulative_data.get(satellite, {})
            if sat_data.get("cumulative_idle"):
                # Get the final cumulative value (last item in the list)
                total += sat_data["cumulative_idle"][-1]
        policy_totals[policy] = total
    
    print("\nTotal idle timesteps by policy:")
    for policy, total in policy_totals.items():
        timestep_duration = config.get('frame_spacing', 1.0)
        total_seconds = total * timestep_duration
        print(f"  {policy}: {total} timesteps ({total_seconds:.1f} seconds)")
    
    # Create output directory with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = SCRIPT_DIR / f"constellation_analysis_{timestamp}"
    output_dir.mkdir(exist_ok=True)
    
    # Set up the plotting style
    plt.style.use('default')
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']
    
    # Create time-based line chart similar to buffer comparison (2x2 subplots for each policy)
    fig, axes = plt.subplots(2, 2, figsize=(28, 24))
    
    # Create enhanced title
    title_lines = ["Satellite Constellation Idle Time Analysis"]
    
    # Add constellation parameters
    sat_count = config.get('satellite_count', 'Unknown')
    frame_spacing = config.get('frame_spacing')
    
    if sat_count != 'Unknown' and frame_spacing:
        title_lines.append(f"{sat_count} Satellites | Frame Rate: 1 image/{frame_spacing:.1f}s")
    
    title_lines.append(f"Cumulative Idle Time Over Time (Connected with Empty Buffer)")
    
    title = '\n'.join(title_lines)
    fig.suptitle(title, fontsize=16, fontweight='bold')
    
    # Get top satellites by final idle time across all policies
    sat_totals = {}
    for satellite in satellites:
        total = 0
        for policy in POLICIES:
            sat_data = results[policy].get(satellite, {})
            if sat_data.get("cumulative_idle"):
                total += sat_data["cumulative_idle"][-1]
        sat_totals[satellite] = total
    
    top_satellites = sorted(sat_totals.items(), key=lambda x: x[1], reverse=True)[:TOP_N]
    
    # Use colors that cycle through the palette for top satellites
    policy_colors = plt.cm.tab20(np.linspace(0, 1, 20))
    
    for i, policy in enumerate(POLICIES):
        ax = axes[i // 2, i % 2]
        
        total_final_idle = policy_totals.get(policy, 0)
        
        legend_data = []
        
        for j, (sat_id, sat_total) in enumerate(top_satellites):
            color = policy_colors[j % len(policy_colors)]
            
            sat_data = results[policy].get(sat_id, {})
            
            if sat_data.get("hours") and sat_data.get("cumulative_idle"):
                # Plot cumulative idle time over hours
                hours = sat_data["hours"]
                cumulative_idle = sat_data["cumulative_idle"]
                final_idle = cumulative_idle[-1] if cumulative_idle else 0
                
                if final_idle > 0:
                    line = ax.plot(hours, cumulative_idle, color=color, linewidth=1.5, 
                                 alpha=0.8, linestyle='solid')[0]
                    legend_data.append((final_idle, line, f'{sat_id} ({final_idle} idle)', False))
                else:
                    # No idle time - use greyed line at zero
                    line = ax.axhline(0, color='lightgray', alpha=0.3, linestyle='--', linewidth=0.5)
                    legend_data.append((0, line, f'{sat_id} (0 idle)', True))
            else:
                # No data - use greyed line at zero
                line = ax.axhline(0, color='lightgray', alpha=0.3, linestyle='--', linewidth=0.5)
                legend_data.append((0, line, f'{sat_id} (0 idle)', True))
        
        # Sort legend: active satellites first (by idle time, highest first), then greyed satellites
        active_legends = [(idle, line, label) for idle, line, label, is_grey in legend_data if not is_grey]
        greyed_legends = [(idle, line, label) for idle, line, label, is_grey in legend_data if is_grey]
        
        # Sort active by idle time (descending), greyed by satellite number (ascending)
        active_legends.sort(key=lambda x: x[0], reverse=True)
        greyed_legends.sort(key=lambda x: x[2])  # Sort by label (contains sat number)
        
        # Combine: active satellites first, then greyed satellites
        sorted_legends = active_legends + greyed_legends
        
        handles = [item[1] for item in sorted_legends]
        labels = [item[2] for item in sorted_legends]
        
        ax.set_xlabel('Time (hours)', fontsize=12)
        ax.set_ylabel('Cumulative Idle Timesteps', fontsize=12)
        ax.set_title(f'{policy.upper()} Scheduling\nTotal Idle Time: {total_final_idle} timesteps', fontweight='bold')
        ax.grid(True, alpha=0.3)
        ax.legend(handles, labels, bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=7)
    
    plt.tight_layout()
    
    # Save line chart
    line_chart_path = output_dir / "idle_time_comparison.png"
    plt.savefig(line_chart_path, dpi=300, bbox_inches='tight')
    print(f"Saved idle time line chart: {line_chart_path}")
    plt.close()
    
    # 2. Bar chart showing total idle time by policy
    fig, ax = plt.subplots(figsize=(10, 6))
    
    policies = list(policy_totals.keys())
    totals = list(policy_totals.values())
    
    bars = ax.bar(policies, totals, color=colors[:len(policies)])
    
    # Add value labels on bars
    for bar, total in zip(bars, totals):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height + max(totals)*0.01,
                f'{int(total)}', ha='center', va='bottom', fontweight='bold')
    
    ax.set_xlabel('Scheduling Policy', fontsize=12)
    ax.set_ylabel('Total Idle Timesteps', fontsize=12)
    ax.set_title('Total Downlink Idle Time by Policy', fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3, axis='y')
    
    # Capitalize policy names
    ax.set_xticklabels([policy.capitalize() for policy in policies])
    
    plt.tight_layout()
    
    # Save bar chart
    bar_chart_path = output_dir / "idle_time_bars.png"
    plt.savefig(bar_chart_path, dpi=300, bbox_inches='tight')
    print(f"Saved idle time bar chart: {bar_chart_path}")
    plt.close()
    
    return output_dir

def main():
    """Main execution function"""
    print("=== Multi-Satellite Downlink Idle Time Analysis ===")
    
    # Read configuration
    config = read_config()
    print(f"Configuration: {config}")
    
    # Analyze idle times
    results, satellites = analyze_idle_times()
    
    if results:
        # Create charts
        output_dir = create_idle_time_charts(results, satellites, config)
        print(f"\nAnalysis complete! Charts saved to: {output_dir}")
    else:
        print("No results generated!")

if __name__ == "__main__":
    main()
