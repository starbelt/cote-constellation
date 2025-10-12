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
import glob
import argparse
import sys
import json
import tempfile

# Configuration - use absolute paths
SCRIPT_DIR = Path(__file__).parent.absolute()
LOGS_DIR = SCRIPT_DIR / "logs"

# Image size aliases and their corresponding values in MB
IMAGE_SIZE_ALIASES = {
    's': 0.027,     # small
    'm': 0.279,     # medium  
    'l': 2.799,     # large
    'xl': 28.0      # extra large
}
POLICIES = ["sticky", "fifo", "roundrobin", "random"]
STRATEGIES = ["close-spaced", "close-orbit-spaced", "frame-spaced", "orbit-spaced"]
TOP_N = 15

def discover_logs(root_dir):
    """Discover constellation analysis folders with format: constellation_analysis_YYYYMMDD_HHMMSS_IMAGESIZE_SATCOUNT"""
    constellation_folders = []
    
    for item in Path(root_dir).iterdir():
        if item.is_dir() and item.name.startswith("constellation_analysis_"):
            constellation_folders.append(item)
    
    # Sort by timestamp (newest first)
    constellation_folders.sort(key=lambda x: x.name, reverse=True)
    return constellation_folders

def parse_folder_path(folder_path):
    """Parse constellation analysis folder name to extract parameters"""
    folder_name = Path(folder_path).name
    
    # Expected format: constellation_analysis_YYYYMMDD_HHMMSS_IMAGESIZE_SATCOUNT
    parts = folder_name.split('_')
    if len(parts) < 5:
        return None
    
    try:
        timestamp = f"{parts[2]}_{parts[3]}"
        # The image size in folder names is scaled by 1000 (e.g., 00279 = 0.279MB)
        image_size_raw = int(parts[4])
        image_size = image_size_raw / 1000.0  # Convert back to MB
        sat_count = int(parts[5])
        
        return {
            'timestamp': timestamp,
            'image_size': image_size,
            'sat_count': sat_count
        }
    except (ValueError, IndexError):
        return None

def resolve_image_size(image_alias_or_value):
    """Resolve image size alias to actual MB value"""
    if isinstance(image_alias_or_value, str) and image_alias_or_value.lower() in IMAGE_SIZE_ALIASES:
        return IMAGE_SIZE_ALIASES[image_alias_or_value.lower()]
    try:
        return float(image_alias_or_value)
    except (ValueError, TypeError):
        return None

def filter_folders_by_parameters(folders, target_sats=None, target_image_size=None):
    """Filter constellation folders by satellite count and image size"""
    filtered = []
    
    for folder in folders:
        params = parse_folder_path(folder)
        if params is None:
            continue
            
        # Check satellite count
        if target_sats is not None and params['sat_count'] != target_sats:
            continue
            
        # Check image size  
        if target_image_size is not None:
            resolved_size = resolve_image_size(target_image_size)
            if resolved_size is None or abs(params['image_size'] - resolved_size) > 0.001:
                continue
                
        filtered.append(folder)
    
    return filtered

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
    """Get satellites with most data loss from overflow files in strategy folder"""
    simulation_logs_zip = strategy_folder / "simulation_logs.zip"
    
    if not simulation_logs_zip.exists():
        print(f"No simulation_logs.zip found in {strategy_folder}")
        return [], {}
    
    policy_dirs = get_policy_dirs(strategy_folder)
    all_totals = {}
    
    with zipfile.ZipFile(simulation_logs_zip, 'r') as zipf:
        for policy in policy_dirs.keys():
            print(f"  Processing {policy} policy...")
            
            # Check overflow files for actual data lost
            overflow_files = [name for name in zipf.namelist() 
                            if name.startswith(f"{policy}/meas-buffer-overflow-sat-") and name.endswith(".csv")]
            
            for overflow_file_path in overflow_files:
                filename = overflow_file_path.split("/")[-1]
                sat_id_raw = filename.replace("meas-buffer-overflow-sat-", "").replace(".csv", "")
                
                # Convert sat_id format: 0060518000 -> 60518000-0
                if len(sat_id_raw) == 10 and sat_id_raw.startswith("00"):
                    sat_id = f"{sat_id_raw[2:]}-0"
                else:
                    sat_id = f"{sat_id_raw}-0"
                
                try:
                    with zipf.open(overflow_file_path) as file:
                        loss_df = pd.read_csv(file)
                        if len(loss_df) > 0:
                            # Get the final (maximum) cumulative loss
                            loss_col = loss_df.columns[1]  # Second column should be loss data
                            final_loss = loss_df[loss_col].iloc[-1]
                            
                            if final_loss > 0:
                                if sat_id not in all_totals:
                                    all_totals[sat_id] = {}
                                all_totals[sat_id][policy] = final_loss
                except Exception as e:
                    pass  # Skip files that can't be read
    
    # Get top satellites by max loss
    if all_totals:
        sat_max = {sat: max(policies.values()) for sat, policies in all_totals.items()}
        top_sats = sorted(sat_max.items(), key=lambda x: x[1], reverse=True)[:TOP_N]
        return [sat for sat, _ in top_sats], all_totals
    else:
        return [], {}

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

def load_loss_data(strategy_folder, policy, satellite_id):
    """Load loss data for satellite from strategy folder"""
    simulation_logs_zip = strategy_folder / "simulation_logs.zip"
    
    if not simulation_logs_zip.exists():
        return None
    
    sat_num = satellite_id.split("-")[0] if "-" in satellite_id else satellite_id
    policy_dirs = get_policy_dirs(strategy_folder)
    
    if policy not in policy_dirs:
        return None
    
    # Convert satellite ID format for overflow file lookup
    # Files are named like meas-buffer-overflow-sat-60518001.csv (no leading zeros)
    sat_id_padded = sat_num  # Don't pad with leading zeros
    overflow_file_path = f"{policy}/meas-buffer-overflow-sat-{sat_id_padded}.csv"
    
    with zipfile.ZipFile(simulation_logs_zip, 'r') as zipf:
        if overflow_file_path not in zipf.namelist():
            return None
            
        with zipf.open(overflow_file_path) as file:
            df = pd.read_csv(file)
            
            if df.empty:
                return None
                
            # Handle 3-column format by taking first 2 columns
            if len(df.columns) == 3:
                df = df.iloc[:, :2]
            
            # Rename columns for clarity - the second column has satellite-specific name
            df.columns = ["timestamp", "cumulative_loss_mb"]
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            
            # Use global time reference for consistent hours across all policies
            global_min_time = get_global_time_reference(strategy_folder)
            df["hours"] = (df["timestamp"] - global_min_time).dt.total_seconds() / 3600
            df["cumulative_loss_mb"] = pd.to_numeric(df["cumulative_loss_mb"], errors='coerce')
            
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
    title_lines = [f"Satellite Constellation Data Loss Analysis - {strategy_name.title()} Strategy"]
    
    # Add constellation parameters
    sat_count = config.get('satellite_count', 'Unknown')
    frame_spacing = config.get('frame_spacing')
    mb_per_sense = config.get('mb_per_sense')
    
    if sat_count != 'Unknown' and frame_spacing and mb_per_sense:
        title_lines.append(f"{sat_count} Satellites | Frame Rate: 1 image/{frame_spacing:.1f}s | Image Size: {mb_per_sense:.2f} MB")
    elif mb_per_sense:
        title_lines.append(f"Image Size: {mb_per_sense:.2f} MB")
    
    title_lines.append(f"Cumulative Data Loss Over Time (All Satellites Per Policy)")
    
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
            
            loss_df = load_loss_data(strategy_folder, policy, sat_id)
            
            if loss_df is None or sat_total == 0:
                # No loss data file found or no data loss - use greyed line at zero
                line = ax.axhline(0, color='lightgray', alpha=0.3, linestyle='--', linewidth=0.5)
                legend_data.append((sat_total, line, f'{sat_id} (0MB)', True))  # True = greyed
            else:
                # Loss data exists - use normal colored line
                line = ax.plot(loss_df['hours'], loss_df['cumulative_loss_mb'], 
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
        ax.set_ylabel('Data Loss (MB)')
        ax.set_title(f'{policy.upper()} Scheduling\nTotal Downloaded: {total_data:.0f} MB', fontweight='bold')
        ax.grid(True, alpha=0.3)
        ax.legend(handles, labels, bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=7)
    
    # Save plot in the constellation analysis folder with strategy-specific naming
    output_filename = f"loss_plot_{strategy_name}_strategy.png"
    output_path = constellation_analysis_folder / output_filename
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"Generated {strategy_name} buffer plot with {len(passes)} orbital passes -> {output_path}")
    return output_path

def main():
    """Main function"""
    print("Multi-Satellite Data Loss Analysis")
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Generate multi-satellite data loss plots')
    parser.add_argument('--sats', type=int, required=True,
                       choices=[1, 50, 100, 200],
                       help='Number of satellites (1, 50, 100, or 200)')
    parser.add_argument('--image', required=True,
                       help='Image size: s/m/l/xl aliases or MB value (e.g., s, m, l, xl, 0.027, 2.799)')
    parser.add_argument('--root-dir', default='../../analysis/',
                       help='Root directory containing constellation_analysis folders (default: ../../analysis/)')
    
    args = parser.parse_args()
    
    # Resolve root directory
    root_dir = Path(args.root_dir)
    if not root_dir.is_absolute():
        root_dir = SCRIPT_DIR / root_dir
    root_dir = root_dir.resolve()
    
    if not root_dir.exists():
        print(f"❌ Error: Root directory '{root_dir}' does not exist!")
        return
    
    print(f"🔍 Searching for constellation analysis folders in: {root_dir}")
    
    # Discover constellation analysis folders
    all_folders = discover_logs(root_dir)
    if not all_folders:
        print("❌ No constellation_analysis folders found!")
        print("Expected folder format: constellation_analysis_YYYYMMDD_HHMMSS_IMAGESIZE_SATCOUNT")
        return
    
    print(f"📁 Found {len(all_folders)} constellation analysis folders")
    
    # Resolve image size
    resolved_image_size = resolve_image_size(args.image)
    if resolved_image_size is None:
        print(f"❌ Error: Invalid image size '{args.image}'. Use s/m/l/xl or a numeric value.")
        return
    
    # Filter by parameters  
    filtered_folders = filter_folders_by_parameters(all_folders, target_sats=args.sats, target_image_size=resolved_image_size)
    
    if not filtered_folders:
        print(f"❌ No folders found matching --sats {args.sats} --image {args.image}")
        print("Available folders:")
        for folder in all_folders[:5]:  # Show first 5
            params = parse_folder_path(folder)
            if params:
                print(f"  {folder.name} (sats: {params['sat_count']}, image: {params['image_size']:.3f}MB)")
        return
    
    # Use the most recent matching folder
    constellation_analysis_folder = filtered_folders[0]
    params = parse_folder_path(constellation_analysis_folder)
    
    print(f"📊 Using folder: {constellation_analysis_folder.name}")
    print(f"   Parameters: {params['sat_count']} satellites, {params['image_size']:.3f} MB images")
    
    # Process each strategy
    generated_plots = []
    for strategy in STRATEGIES:
        strategy_folder = constellation_analysis_folder / strategy
        if strategy_folder.exists():
            print(f"\n🔄 Processing {strategy} strategy...")
            try:
                output_path = create_plot(strategy_folder, strategy, constellation_analysis_folder)
                if output_path:
                    generated_plots.append(output_path)
            except Exception as e:
                print(f"❌ Error processing {strategy} strategy: {e}")
        else:
            print(f"⚠️  Strategy folder not found: {strategy}")
    
    if generated_plots:
        print(f"\n✅ Data Loss analysis complete! Generated {len(generated_plots)} plots:")
        for plot_path in generated_plots:
            print(f"   📈 {plot_path}")
    else:
        print("❌ No plots were generated.")
        
    return generated_plots

if __name__ == "__main__":
    main()
