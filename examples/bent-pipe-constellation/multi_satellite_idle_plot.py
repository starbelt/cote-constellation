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
import glob
import argparse
import sys
import tempfile
import re

# Configuration - use absolute paths
SCRIPT_DIR = Path(__file__).parent.absolute()
LOGS_DIR = SCRIPT_DIR / "logs"
POLICIES = ["sticky", "fifo", "roundrobin", "random"]
STRATEGIES = ["close-spaced", "close-orbit-spaced", "frame-spaced", "orbit-spaced"]
TOP_N = 15

# Image size aliases
IMAGE_ALIASES = {
    's': 0.027,
    'm': 0.279,
    'l': 2.799,
    'xl': 28.0
}

def normalize_name(name, target_list):
    """Normalize name to match one from target_list, handling case/hyphen/underscore variations"""
    if not name:
        return None
    
    # Clean the input name
    clean_name = name.strip().replace('_', '-').replace(' ', '-')
    
    # Try exact match first
    for target in target_list:
        if clean_name.lower() == target.lower():
            return target
    
    # Try partial matches
    for target in target_list:
        target_clean = target.lower().replace('-', '').replace(' ', '')
        name_clean = clean_name.lower().replace('-', '').replace(' ', '')
        if target_clean == name_clean:
            return target
    
    return None

def parse_folder_path(path):
    """Parse folder path to extract sats, image_size, policy, spacing"""
    path_str = str(path)
    
    # Look for constellation_analysis pattern first
    constellation_match = re.search(r'constellation_analysis_\d+_\d+_(\d+)_(\d+)', path_str)
    if constellation_match:
        # Format: constellation_analysis_YYYYMMDD_HHMMSS_IMAGESIZE_SATCOUNT
        image_size_str = constellation_match.group(1)
        sat_count_str = constellation_match.group(2)
        
        try:
            # Image size (5-digit format like 00027, 00279, 02799, 28000)
            image_size = float(image_size_str) / 1000.0  # Convert to MB
            sat_count = int(sat_count_str)
            
            return {
                'sats': sat_count,
                'image_size': image_size,
                'policy': None,  # Will be filled in by discover_logs
                'spacing': None  # Will be filled in by discover_logs
            }
        except (ValueError, IndexError):
            pass
    
    return None

def discover_logs(root_dir="."):
    """Discover all simulation logs and extract metadata"""
    root_path = Path(root_dir)
    logs = []
    
    print(f"Searching for visibility logs in: {root_path.absolute()}")
    
    # Find all constellation_analysis folders
    constellation_folders = list(root_path.glob('constellation_analysis_*'))
    
    for constellation_folder in constellation_folders:
        # Parse constellation folder metadata
        constellation_meta = parse_folder_path(constellation_folder)
        if not constellation_meta:
            continue
            
        # Look for strategy folders
        for strategy in STRATEGIES:
            strategy_folder = constellation_folder / strategy
            if not strategy_folder.exists():
                continue
                
            # Check for simulation_logs.zip
            sim_logs_zip = strategy_folder / "simulation_logs.zip"
            if not sim_logs_zip.exists():
                continue
                
            # Look inside the zip for policy folders with visibility logs
            try:
                with zipfile.ZipFile(sim_logs_zip, 'r') as zipf:
                    for policy in POLICIES:
                        # Check if this policy has visibility log
                        visibility_log_path = f"{policy}/visibility_log.csv"
                        
                        if visibility_log_path in zipf.namelist():
                            log_entry = {
                                'constellation_folder': constellation_folder,
                                'strategy_folder': strategy_folder,
                                'simulation_logs_zip': sim_logs_zip,
                                'sats': constellation_meta['sats'],
                                'image_size': constellation_meta['image_size'],
                                'policy': policy,
                                'spacing': strategy
                            }
                            logs.append(log_entry)
            except Exception as e:
                print(f"Error reading {sim_logs_zip}: {e}")
                continue
    
    print(f"Found {len(logs)} total logs")
    return logs

def resolve_image_size(image_input):
    """Resolve image size from user input (number or alias)"""
    if isinstance(image_input, str) and image_input.lower() in IMAGE_ALIASES:
        return IMAGE_ALIASES[image_input.lower()]
    try:
        return float(image_input)
    except (ValueError, TypeError):
        return None

def extract_constellation_data(folder_path=None):
    """Extract data from specified or latest constellation_analysis folder"""
    if folder_path:
        # Use specified folder
        if isinstance(folder_path, str):
            folder_path = Path(folder_path)
        
        # Handle both absolute and relative paths
        if not folder_path.is_absolute():
            folder_path = SCRIPT_DIR / folder_path
            
        if not folder_path.exists():
            print(f"❌ Specified folder not found: {folder_path}")
            return None
            
        if not folder_path.name.startswith('constellation_analysis_'):
            print(f"❌ Folder doesn't appear to be a constellation analysis folder: {folder_path}")
            return None
            
        print(f"📁 Using specified constellation analysis folder: {folder_path.name}")
        return folder_path
    else:
        # Find latest folder (existing behavior)
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
        print(f"📁 Using latest constellation analysis folder: {latest_folder.name}")
        
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

def get_active_satellites(strategy_folder):
    """Get satellites that have any downlink activity from strategy folder"""
    simulation_logs_zip = strategy_folder / "simulation_logs.zip"
    
    if not simulation_logs_zip.exists():
        return []
    
    policy_dirs = get_policy_dirs(strategy_folder)
    all_satellites = set()
    
    with zipfile.ZipFile(simulation_logs_zip, 'r') as zipf:
        for policy in policy_dirs.keys():
            tx_rx_file_path = f"{policy}/meas-downlink-tx-rx.csv"
            if tx_rx_file_path in zipf.namelist():
                with zipf.open(tx_rx_file_path) as file:
                    tx_rx_df = pd.read_csv(file)
                    tx_rx_df = tx_rx_df.iloc[:, :2]
                    tx_rx_df.columns = ["timestamp", "satellite"]
                    
                    # Get unique satellites (excluding None/NaN)
                    satellites = tx_rx_df["satellite"].dropna()
                    satellites = satellites[satellites != "None"]
                    all_satellites.update(satellites.unique())
    
    return sorted(list(all_satellites))

def calculate_cumulative_idle_time_for_policy_efficient(strategy_folder, policy, satellites):
    """Calculate cumulative idle time using efficient visibility_log.csv method"""
    print(f"    Calculating cumulative idle time for {policy} (efficient method)...")
    
    simulation_logs_zip = strategy_folder / "simulation_logs.zip"
    
    if not simulation_logs_zip.exists():
        return {}
    
    cumulative_idle_data = {}
    
    # Use temporary directory for zip extraction
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        with zipfile.ZipFile(simulation_logs_zip, 'r') as zipf:
            # Extract only the policy directory we need
            policy_files = [name for name in zipf.namelist() if name.startswith(f"{policy}/")]
            for file_name in policy_files:
                zipf.extract(file_name, temp_path)
        
        visibility_log_path = temp_path / policy / "visibility_log.csv"
        
        if not visibility_log_path.exists():
            print(f"    No visibility log found for {policy}")
            return {sat: {"hours": [], "cumulative_idle": []} for sat in satellites}
        
        # Read visibility log
        df = pd.read_csv(visibility_log_path)
        
        if len(df) == 0:
            return {sat: {"hours": [], "cumulative_idle": []} for sat in satellites}
        
        print(f"    Loaded {len(df)} visibility log entries")
        
        # Check for connected entries
        connected_df = df[df['connected'] == 1]
        print(f"    Found {len(connected_df)} connected entries")
        
        # Check for idle entries (connected AND buffer near 0)
        idle_df = connected_df[connected_df['buffer_mb'] <= 0.001]
        print(f"    Found {len(idle_df)} idle entries")
        
        # Convert time to hours from start
        df['time'] = pd.to_numeric(df['time'], errors='coerce')
        start_time = df['time'].min()
        df['hours'] = (df['time'] - start_time) / 3600  # Convert seconds to hours
        
        # Process each satellite
        total_idle_found = 0
        for satellite in satellites:
            # Convert satellite ID format for visibility log lookup
            # Original format: 60518000-0, visibility log format: 60518000 (as integer)
            if satellite.endswith("-0"):
                sat_id_for_lookup = int(satellite[:-2])  # Remove "-0" and convert to int
            else:
                sat_id_for_lookup = int(satellite)  # Convert to int
            
            # Filter data for this satellite
            sat_data = df[df['sat_id'] == sat_id_for_lookup].copy()
            
            if len(sat_data) == 0:
                cumulative_idle_data[satellite] = {"hours": [], "cumulative_idle": []}
                continue
            
            # Calculate cumulative idle time: connected AND buffer <= 0.001 MB
            # This is the same logic as the original but much more efficient
            sat_data['is_idle'] = (sat_data['connected'] == 1) & (sat_data['buffer_mb'] <= 0.001)
            sat_data['cumulative_idle'] = sat_data['is_idle'].cumsum()
            
            # Extract the time series
            hours_list = sat_data['hours'].tolist()
            cumulative_idle_list = sat_data['cumulative_idle'].tolist()
            
            cumulative_idle_data[satellite] = {
                "hours": hours_list,
                "cumulative_idle": cumulative_idle_list
            }
            
            total_idle = cumulative_idle_list[-1] if cumulative_idle_list else 0
            total_idle_found += total_idle
            if total_idle > 0:
                print(f"      Satellite {satellite}: {total_idle} total idle timesteps")
    
    return cumulative_idle_data

def analyze_idle_times(strategy_folder):
    """Analyze idle times for all policies in strategy folder"""
    print("Analyzing downlink idle times...")
    
    policy_dirs = get_policy_dirs(strategy_folder)
    if not policy_dirs:
        print("No policy directories found!")
        return None, None
    
    # Get all active satellites
    satellites = get_active_satellites(strategy_folder)
    print(f"Found {len(satellites)} active satellites")
    
    results = {}
    
    for policy in policy_dirs.keys():
        print(f"  Processing {policy} policy...")
        cumulative_data = calculate_cumulative_idle_time_for_policy_efficient(strategy_folder, policy, satellites)
        results[policy] = cumulative_data
    
    return results, satellites

def create_idle_time_charts(strategy_folder, strategy_name, constellation_analysis_folder, results, satellites, config):
    """Create idle time comparison charts for a specific strategy"""
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
    
    print(f"\nTotal idle timesteps by policy for {strategy_name}:")
    for policy, total in policy_totals.items():
        timestep_duration = config.get('frame_spacing', 1.0)
        total_seconds = total * timestep_duration
        print(f"  {policy}: {total} timesteps ({total_seconds:.1f} seconds)")
    
    # Set up the plotting style
    plt.style.use('default')
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']
    
    # Create time-based line chart similar to buffer comparison (2x2 subplots for each policy)
    fig, axes = plt.subplots(2, 2, figsize=(28, 24))
    
    # Create enhanced title
    title_lines = [f"Satellite Constellation Idle Time Analysis - {strategy_name.title()} Strategy"]
    
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
    
    # Save to constellation_analysis/idle_plots/ directory
    output_dir = SCRIPT_DIR / "constellation_analysis" / "idle_plots"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Include constellation name in filename
    constellation_name = constellation_analysis_folder.name
    output_filename = f"idle_plot_{constellation_name}_{strategy_name}_strategy.png"
    output_path = output_dir / output_filename
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"✅ Generated {strategy_name} idle plot -> {output_filename}")
    return output_path

def main():
    """Main function with satellite count and image size filtering"""
    parser = argparse.ArgumentParser(description='Generate satellite idle time analysis plots')
    parser.add_argument('--root-dir', default='.', help='Root directory to search for constellation analysis folders')
    parser.add_argument('--sats', type=int, required=True, help='Number of satellites to filter by')
    parser.add_argument('--image', required=True, help='Image size to filter by (number in MB or alias: s, m, l, xl)')
    args = parser.parse_args()
    
    # Resolve image size
    target_image = resolve_image_size(args.image)
    if target_image is None:
        print(f"Error: Invalid image size '{args.image}'. Use a number (MB) or alias: s, m, l, xl")
        return 1
    
    print("Multi-Satellite Idle Time Analysis")
    print(f"Filtering by: {args.sats} satellites, {target_image:.3f}MB image size")
    
    # Discover all logs
    all_logs = discover_logs(args.root_dir)
    if not all_logs:
        print("❌ No constellation analysis data found!")
        return 1
    
    # Show available parameters
    available_sats = sorted(set(log['sats'] for log in all_logs))
    available_images = sorted(set(log['image_size'] for log in all_logs))
    print(f"Available satellite counts: {available_sats}")
    print(f"Available image sizes: {available_images}")
    
    # Filter logs by satellite count and image size
    filtered_logs = []
    for log in all_logs:
        if log['sats'] == args.sats and abs(log['image_size'] - target_image) < 0.001:
            filtered_logs.append(log)
    
    if not filtered_logs:
        print(f"❌ No logs found for sats={args.sats}, image={target_image:.3f}MB")
        return 1
    
    print(f"Found {len(filtered_logs)} logs for sats={args.sats}, image={target_image:.3f}MB")
    
    # Group logs by constellation folder (same analysis run)
    constellation_groups = {}
    for log in filtered_logs:
        folder_key = log['constellation_folder']
        if folder_key not in constellation_groups:
            constellation_groups[folder_key] = []
        constellation_groups[folder_key].append(log)
    
    # Process each constellation analysis folder
    generated_plots = []
    for constellation_folder, logs_in_folder in constellation_groups.items():
        print(f"\nProcessing constellation analysis folder: {constellation_folder.name}")
        
        # Group by strategy within this constellation folder
        strategy_groups = {}
        for log in logs_in_folder:
            strategy = log['spacing']
            if strategy not in strategy_groups:
                strategy_groups[strategy] = []
            strategy_groups[strategy].append(log)
        
        # Process each strategy
        for strategy, strategy_logs in strategy_groups.items():
            print(f"  Processing {strategy} strategy...")
            try:
                # Use the first log's strategy_folder for the strategy
                strategy_folder = strategy_logs[0]['strategy_folder']
                
                # Analyze idle times for this strategy
                results, satellites = analyze_idle_times(strategy_folder)
                if results:
                    # Read configuration
                    config = read_config()
                    
                    # Generate plot
                    output_path = create_idle_time_charts(strategy_folder, strategy, constellation_folder, results, satellites, config)
                    if output_path:
                        generated_plots.append(output_path)
            except Exception as e:
                print(f"  Error processing {strategy} strategy: {e}")
    
    if generated_plots:
        print(f"\nIdle time analysis complete! Generated {len(generated_plots)} plots:")
        for plot_path in generated_plots:
            print(f"  {plot_path}")
    else:
        print("No plots were generated.")
    
    return 0

if __name__ == "__main__":
    exit(main())
