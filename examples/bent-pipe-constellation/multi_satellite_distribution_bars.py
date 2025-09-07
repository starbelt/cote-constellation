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
    """Create comprehensive bar chart analysis"""
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
    
    # Create single figure for policy comparison - make it bigger for better readability
    fig, ax = plt.subplots(1, 1, figsize=(20, 12))
    
    # Create enhanced title
    title_lines = ["Satellite Constellation Data Distribution Analysis"]
    
    # Add constellation parameters
    sat_count = config.get('satellite_count', 'Unknown')
    frame_spacing = config.get('frame_spacing')
    mb_per_sense = config.get('mb_per_sense')
    
    if sat_count != 'Unknown' and frame_spacing and mb_per_sense:
        title_lines.append(f"{sat_count} Satellites | Frame Rate: 1 image/{frame_spacing:.1f}s | Image Size: {mb_per_sense:.2f} MB")
    elif mb_per_sense:
        title_lines.append(f"Image Size: {mb_per_sense:.2f} MB")
    
    title_lines.append(f"Total Data Downloaded by Policy and Orbital Pass ({len(passes)} Passes)")
    
    title = '\\n'.join(title_lines)
    fig.suptitle(title, fontsize=16, fontweight='bold')
    
    # Prepare data for stacked bar chart - policies on x-axis, stacked by pass
    policy_labels = [policy.upper() for policy in POLICIES if policy in pass_results]
    pass_colors = plt.cm.viridis(np.linspace(0, 1, len(passes)))
    
    # Collect data for each policy and pass
    policy_pass_data = {}
    policy_totals = {}
    policy_satellites_served = {}
    policy_satellites_per_pass = {}  # Track satellites per pass
    policy_satellite_ids_per_pass = {}  # NEW: Track actual satellite IDs per pass
    
    for policy in POLICIES:
        if policy not in pass_results:
            continue
            
        policy_data = pass_results[policy]
        pass_data_list = []
        pass_satellite_counts = []  # Satellite count per pass
        pass_satellite_ids = []  # NEW: Satellite IDs per pass
        total_data = 0
        all_satellites_used = set()
        
        for pass_idx in range(len(passes)):
            if pass_idx in policy_data:
                pass_total = policy_data[pass_idx]['total']
                pass_satellites = list(policy_data[pass_idx]['satellites'].keys())  # Get satellite IDs
                pass_data_list.append(pass_total)
                pass_satellite_counts.append(len(pass_satellites))
                pass_satellite_ids.append(pass_satellites)  # Store actual satellite IDs
                total_data += pass_total
                all_satellites_used.update(pass_satellites)
            else:
                pass_data_list.append(0)
                pass_satellite_counts.append(0)
                pass_satellite_ids.append([])  # Empty list for no satellites
        
        policy_pass_data[policy] = pass_data_list
        policy_satellites_per_pass[policy] = pass_satellite_counts
        policy_satellite_ids_per_pass[policy] = pass_satellite_ids  # NEW: store satellite IDs
        policy_totals[policy] = total_data
        policy_satellites_served[policy] = len(all_satellites_used)
    
    # Create stacked bar chart
    x_positions = np.arange(len(policy_labels))
    width = 0.6
    
    # Stack passes for each policy
    bottom = np.zeros(len(policy_labels))
    
    for pass_idx in range(len(passes)):
        pass_values = []
        pass_satellite_counts = []  # New: collect satellite counts for this pass
        pass_satellite_ids = []  # NEW: collect satellite IDs for this pass
        
        for policy in POLICIES:
            if policy in policy_pass_data:
                pass_values.append(policy_pass_data[policy][pass_idx])
                pass_satellite_counts.append(policy_satellites_per_pass[policy][pass_idx])
                pass_satellite_ids.append(policy_satellite_ids_per_pass[policy][pass_idx])
            else:
                pass_values.append(0)
                pass_satellite_counts.append(0)
                pass_satellite_ids.append([])
        
        bars = ax.bar(x_positions, pass_values, width, bottom=bottom, 
                     label=f'Pass {pass_idx + 1}', color=pass_colors[pass_idx], alpha=0.8)
        
        # Add detailed labels on each stack segment with satellite count and IDs
        for i, (bar, sat_count, sat_ids, value) in enumerate(zip(bars, pass_satellite_counts, pass_satellite_ids, pass_values)):
            if value > 0:  # Only add label if there's data
                # Calculate the center of this stack segment
                segment_center = bottom[i] + value / 2
                
                # Create label text with data amount, satellite count, and satellite IDs
                label_parts = [f'{value:.0f} MB']
                if sat_count > 0:
                    label_parts.append(f'{sat_count} sats')
                    
                    # Add satellite IDs - limit to first few that will fit
                    if sat_ids:
                        # Sort satellite IDs for consistent display
                        sorted_sat_ids = sorted(sat_ids)
                        
                        # Determine how many satellite IDs to show based on available space
                        # Estimate based on segment height and font size
                        segment_height = value
                        max_height = max(policy_totals.values()) if policy_totals else 1000
                        relative_height = segment_height / max_height
                        
                        # Show more IDs for larger segments
                        if relative_height > 0.15:  # Large segment
                            max_ids_to_show = min(8, len(sorted_sat_ids))
                        elif relative_height > 0.08:  # Medium segment
                            max_ids_to_show = min(4, len(sorted_sat_ids))
                        elif relative_height > 0.04:  # Small segment
                            max_ids_to_show = min(2, len(sorted_sat_ids))
                        else:  # Very small segment
                            max_ids_to_show = 0
                        
                        if max_ids_to_show > 0:
                            ids_to_show = sorted_sat_ids[:max_ids_to_show]
                            ids_text = ', '.join(ids_to_show)
                            if len(sorted_sat_ids) > max_ids_to_show:
                                ids_text += f', +{len(sorted_sat_ids) - max_ids_to_show}'
                            label_parts.append(f'({ids_text})')
                
                label_text = '\n'.join(label_parts)
                
                # Choose text color for visibility
                text_color = 'white' if pass_idx < 3 else 'black'
                
                # Add label with enhanced information
                ax.text(bar.get_x() + bar.get_width()/2, segment_center, 
                       label_text, 
                       ha='center', va='center', fontweight='bold', 
                       fontsize=8, color=text_color,
                       bbox=dict(boxstyle='round,pad=0.2', facecolor='black', alpha=0.6) if pass_idx >= 3 else None)
        
        bottom += np.array(pass_values)
    
    # Customize the chart with better styling
    ax.set_xlabel('Scheduling Policy', fontweight='bold', fontsize=14)
    ax.set_ylabel('Data Downloaded (MB)', fontweight='bold', fontsize=14)
    ax.set_xticks(x_positions)
    ax.set_xticklabels(policy_labels, fontsize=12, fontweight='bold')
    ax.grid(True, alpha=0.3, axis='y', linestyle='--')
    ax.legend(title='Orbital Passes', bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=11)
    
    # Make tick labels larger
    ax.tick_params(axis='y', labelsize=11)
    
    # Add clear summary labels at the top of each bar
    for i, policy in enumerate(POLICIES):
        if policy in policy_totals:
            total = policy_totals[policy]
            sats = policy_satellites_served[policy]
            
            # Add bold summary text above each bar
            ax.text(i, total + max(policy_totals.values()) * 0.02, 
                   f'{total:.0f} MB Total Down\n{sats} Sats Downlinked', 
                   ha='center', va='bottom', fontweight='bold', fontsize=14,
                   bbox=dict(boxstyle='round,pad=0.5', facecolor='lightblue', alpha=0.8, edgecolor='navy'))
    
    # Set y-axis limit to accommodate text - give more space for the summary labels
    max_total = max(policy_totals.values()) if policy_totals else 1000
    ax.set_ylim(0, max_total * 1.25)
    
    plt.tight_layout()
    plt.savefig(output_dir / "satellite_distribution_bars.png", dpi=300, bbox_inches='tight')
    plt.close()
    
    if output_dir and output_dir.parent == SCRIPT_DIR:  # Only print if we created our own directory
        print(f"Generated satellite distribution bar chart -> {output_dir}/satellite_distribution_bars.png")

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
