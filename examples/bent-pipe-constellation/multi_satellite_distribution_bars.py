#!/usr/bin/env python3
"""
Multi-Satellite Data Distribution Bar Chart Analysis

Shows total data downloaded per satellite per orbital pass with stacked bars
and summary statistics for satellites served per policy.
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

def analyze_satellite_data_per_pass():
    """Analyze satellite data distribution per orbital pass"""
    policy_dirs = get_policy_dirs()
    passes = get_orbital_passes()
    global_min_time = get_global_time_reference()
    
    results = {}
    
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
        tx_rx_df["hours"] = (tx_rx_df["timestamp"] - global_min_time).dt.total_seconds() / 3600
        mbps_df["mbps"] = pd.to_numeric(mbps_df["mbps"], errors='coerce')
        
        # Convert to lists for index-based matching
        tx_rx_list = tx_rx_df.to_dict('records')
        mbps_list = mbps_df.to_dict('records')
        
        # Analyze data per pass
        pass_data = {}
        for pass_idx, (start_hour, end_hour) in enumerate(passes):
            pass_data[pass_idx] = {'satellites': {}, 'total': 0}
            
            for i, tx_row in enumerate(tx_rx_list):
                sat = tx_row["satellite"]
                hour = tx_row["hours"]
                
                if pd.isna(sat) or sat == "None":
                    continue
                    
                # Check if this transmission is within the current pass
                if start_hour <= hour <= end_hour:
                    # Use index-based matching for Mbps data
                    if i < len(mbps_list):
                        mbps = mbps_list[i]["mbps"]
                        if pd.notna(mbps) and mbps > 0:
                            data_mb = mbps * 100 / 8  # 100s timestep
                            
                            if sat not in pass_data[pass_idx]['satellites']:
                                pass_data[pass_idx]['satellites'][sat] = 0
                            pass_data[pass_idx]['satellites'][sat] += data_mb
                            pass_data[pass_idx]['total'] += data_mb
        
        results[policy] = pass_data
    
    return results, passes

def create_bar_chart(output_dir=None):
    """Create clean bar chart showing total data downloaded per policy"""
    config = read_config()
    pass_results, passes = analyze_satellite_data_per_pass()
    
    if not pass_results:
        print("No satellite data found for bar chart!")
        return
    
    # Save plot - use provided output directory or create timestamped one
    if output_dir is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = SCRIPT_DIR / f"analysis_{timestamp}"
        output_dir.mkdir(exist_ok=True)
    
    # Set consistent font family for the entire plot
    plt.rcParams['font.family'] = 'DejaVu Sans'
    plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'Helvetica', 'sans-serif']
    
    # Create figure - cleaner layout for simple bar chart
    fig, ax = plt.subplots(1, 1, figsize=(12, 8))
    
    # Calculate totals and statistics for each policy
    policy_totals = {}
    policy_satellites_served = {}
    policy_passes_active = {}
    
    for policy in POLICIES:
        if policy not in pass_results:
            continue
            
        policy_data = pass_results[policy]
        total_data = 0
        all_satellites_used = set()
        active_passes = 0
        
        for pass_idx in range(len(passes)):
            if pass_idx in policy_data and policy_data[pass_idx]['total'] > 0:
                total_data += policy_data[pass_idx]['total']
                all_satellites_used.update(policy_data[pass_idx]['satellites'].keys())
                active_passes += 1
        
        policy_totals[policy] = total_data
        policy_satellites_served[policy] = len(all_satellites_used)
        policy_passes_active[policy] = active_passes
    
    # Sort policies by total data downloaded (most first - winner first)
    sorted_policies = sorted([p for p in POLICIES if p in policy_totals], 
                           key=lambda p: policy_totals[p], reverse=True)
    
    # Create data for plotting
    policy_labels = [policy.upper() for policy in sorted_policies]
    data_values = [policy_totals[policy] for policy in sorted_policies]
    satellite_counts = [policy_satellites_served[policy] for policy in sorted_policies]
    
    # Use a gradient of blues for the bars (darker for better performance)
    bar_colors = ['#08306b', '#2171b5', '#4292c6', '#6baed6'][:len(sorted_policies)]
    
    # Create the bar chart
    x_positions = np.arange(len(policy_labels))
    bars = ax.bar(x_positions, data_values, color=bar_colors, alpha=0.8, width=0.6)
    
    # Add value labels on top of each bar
    for i, (bar, policy, satellites) in enumerate(zip(bars, sorted_policies, satellite_counts)):
        height = bar.get_height()
        bar_bottom = bar.get_y()  # Get the bottom of the bar (might not be 0)
        bar_height = height - bar_bottom  # Actual visual height of the bar
        
        # Main data label - position relative to bar height
        ax.text(bar.get_x() + bar.get_width()/2, height + (max(data_values) - min(data_values)) * 0.02,
               f'{height:.1f} MB',
               ha='center', va='bottom', fontweight='bold', fontsize=14,
               family='DejaVu Sans', color='#08306b')
        
        # Satellite count label in the middle of the visible bar
        middle_y = bar_bottom + bar_height * 0.5
        ax.text(bar.get_x() + bar.get_width()/2, middle_y,
               f'{satellites} satellites',
               ha='center', va='center', fontweight='bold', fontsize=12,
               family='DejaVu Sans', color='white',
               bbox=dict(boxstyle='round,pad=0.3', facecolor='black', alpha=0.7))
    
    # Create enhanced title
    title_lines = ["Satellite Constellation Scheduling Policy Performance"]
    
    # Add constellation parameters
    sat_count = config.get('satellite_count', 'Unknown')
    frame_spacing = config.get('frame_spacing')
    mb_per_sense = config.get('mb_per_sense')
    
    if sat_count != 'Unknown' and frame_spacing and mb_per_sense:
        title_lines.append(f"{sat_count} Satellites | Frame Rate: 1 image/{frame_spacing:.1f}s | Image Size: {mb_per_sense:.2f} MB")
    elif mb_per_sense:
        title_lines.append(f"Image Size: {mb_per_sense:.2f} MB")
    
    title_lines.append(f"Total Data Downloaded Across {len(passes)} Orbital Passes")
    
    title = '\n'.join(title_lines)
    fig.suptitle(title, fontsize=16, fontweight='bold', family='DejaVu Sans')
    
    # Customize the chart
    ax.set_xlabel('Scheduling Policy (Ordered by Performance)', fontweight='bold', fontsize=14, family='DejaVu Sans')
    ax.set_ylabel('Total Data Downloaded (MB)', fontweight='bold', fontsize=14, family='DejaVu Sans')
    ax.set_xticks(x_positions)
    ax.set_xticklabels(policy_labels, fontsize=12, fontweight='bold', family='DejaVu Sans')
    
    # Add horizontal grid for easier reading
    ax.grid(True, alpha=0.3, axis='y', linestyle='--')
    ax.set_axisbelow(True)
    
    # Style the axes
    ax.tick_params(axis='y', labelsize=11)
    for label in ax.get_yticklabels():
        label.set_family('DejaVu Sans')
    
    # Smart y-axis scaling to show differences better
    if data_values:
        max_value = max(data_values)
        min_value = min(data_values)
        value_range = max_value - min_value
        
        # If values are very close (difference < 5% of max), zoom in
        if value_range / max_value < 0.05:
            # Start y-axis at 90% of minimum value to show differences
            y_min = min_value * 0.9
            y_max = max_value * 1.05
        else:
            # Use normal scaling when differences are significant
            y_min = 0
            y_max = max_value * 1.15
        
        ax.set_ylim(y_min, y_max)
        
        # Adjust bar chart to start from y_min when zoomed
        if y_min > 0:
            # Re-create bars with bottom starting at y_min
            ax.clear()
            
            # Re-apply styling after clearing
            bars = ax.bar(x_positions, [v - y_min for v in data_values], 
                         bottom=y_min, color=bar_colors, alpha=0.8, width=0.6)
            
            # Re-add labels and styling
            ax.set_xlabel('Scheduling Policy (Ordered by Performance)', fontweight='bold', fontsize=14, family='DejaVu Sans')
            ax.set_ylabel('Total Data Downloaded (MB)', fontweight='bold', fontsize=14, family='DejaVu Sans')
            ax.set_xticks(x_positions)
            ax.set_xticklabels(policy_labels, fontsize=12, fontweight='bold', family='DejaVu Sans')
            ax.grid(True, alpha=0.3, axis='y', linestyle='--')
            ax.set_axisbelow(True)
            ax.tick_params(axis='y', labelsize=11)
            for label in ax.get_yticklabels():
                label.set_family('DejaVu Sans')
            ax.set_ylim(y_min, y_max)
    else:
        ax.set_ylim(0, 1000)
    
    # Add value labels on top of each bar (after potential re-creation)
    for i, (bar, policy, satellites, value) in enumerate(zip(bars, sorted_policies, satellite_counts, data_values)):
        # Main data label
        ax.text(bar.get_x() + bar.get_width()/2, value + (max(data_values) - min(data_values)) * 0.02,
               f'{value:.1f} MB',
               ha='center', va='bottom', fontweight='bold', fontsize=14,
               family='DejaVu Sans', color='#08306b')
        
        # Satellite count label in the middle of the bar
        bar_middle = (bar.get_height() / 2) + bar.get_y()
        ax.text(bar.get_x() + bar.get_width()/2, bar_middle,
               f'{satellites} satellites',
               ha='center', va='center', fontweight='bold', fontsize=12,
               family='DejaVu Sans', color='white',
               bbox=dict(boxstyle='round,pad=0.3', facecolor='black', alpha=0.7))
    
    plt.tight_layout()
    plt.savefig(output_dir / "satellite_distribution_bars.png", dpi=300, bbox_inches='tight')
    plt.close()
    
    # Reset matplotlib settings to default
    plt.rcParams.update(plt.rcParamsDefault)
    
    if output_dir and output_dir.parent == SCRIPT_DIR:  # Only print if we created our own directory
        print(f"Generated satellite distribution bar chart -> {output_dir}/satellite_distribution_bars.png")
        print(f"Performance ranking: {' > '.join([p.upper() for p in sorted_policies])}")
        print(f"For detailed pass-by-pass analysis, use the buffer plot or loss plot scripts.")

def main():
    """Main function"""
    print("Multi-Satellite Data Distribution Bar Chart Analysis")
    
    policy_dirs = get_policy_dirs()
    if not policy_dirs:
        print("No simulation logs found!")
        print("Please run simulations first using the scripts in the scripts/ directory.")
        return
    
    create_bar_chart()  # Use default behavior when run standalone

if __name__ == "__main__":
    main()
