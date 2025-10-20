#!/usr/bin/env python3
"""
Multi-Satellite Buffer Analysis V2

Uses visibility_log.csv for accurate buffer tracking and download data.
Matches the exact look and feel of the original multi_satellite_buffer_plot.py
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import zipfile
import argparse
import sys
import re

# Configuration
SCRIPT_DIR = Path(__file__).parent.absolute()
POLICIES = ["sticky", "fifo", "roundrobin", "random"]
STRATEGIES = ["close-spaced", "close-orbit-spaced", "frame-spaced", "orbit-spaced"]

# Image size aliases
IMAGE_ALIASES = {
    's': 0.027,
    'm': 0.279,
    'l': 2.799,
    'xl': 28.0
}

def normalize_name(name, target_list):
    """Normalize name to match one from target_list"""
    if not name:
        return None
    
    clean_name = name.strip().replace('_', '-').replace(' ', '-')
    
    for target in target_list:
        if clean_name.lower() == target.lower():
            return target
    
    for target in target_list:
        if clean_name.lower() in target.lower() or target.lower() in clean_name.lower():
            return target
    
    return None

def parse_constellation_folder(folder_name):
    """Parse constellation folder name to extract metadata"""
    # Format: constellation_analysis_YYYYMMDD_HHMMSS_IMAGESIZE_NUMSATS
    match = re.match(r'constellation_analysis_(\d{8})_(\d{6})_(\d+)_(\d+)', folder_name)
    if match:
        image_mb = float(match.group(3)) / 1000.0
        sats = int(match.group(4))
        return {'image_size': image_mb, 'sats': sats}
    return None

def scan_for_logs(root_dir='.'):
    """Scan for constellation analysis folders with visibility_log.csv"""
    root_path = Path(root_dir).absolute()
    constellation_folders = sorted(root_path.glob("constellation_analysis_*"))
    
    logs = []
    for constellation_folder in constellation_folders:
        constellation_meta = parse_constellation_folder(constellation_folder.name)
        if not constellation_meta:
            continue
            
        for strategy in STRATEGIES:
            strategy_folder = constellation_folder / strategy
            if not strategy_folder.exists():
                continue
                
            sim_logs_zip = strategy_folder / "simulation_logs.zip"
            if not sim_logs_zip.exists():
                continue
                
            try:
                with zipfile.ZipFile(sim_logs_zip, 'r') as zipf:
                    for policy in POLICIES:
                        vis_log_path = f"{policy}/visibility_log.csv"
                        if vis_log_path in zipf.namelist():
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
    
    return logs

def resolve_image_size(image_input):
    """Resolve image size from user input"""
    if isinstance(image_input, str) and image_input.lower() in IMAGE_ALIASES:
        return IMAGE_ALIASES[image_input.lower()]
    try:
        return float(image_input)
    except (ValueError, TypeError):
        return None

def read_config(zip_path, policy):
    """Read configuration from simulation zip"""
    config = {}
    
    with zipfile.ZipFile(zip_path, 'r') as zipf:
        # Try sensor.dat
        sensor_path = f"{policy}/sensor.dat"
        if sensor_path in zipf.namelist():
            with zipf.open(sensor_path) as f:
                lines = f.read().decode('utf-8').strip().split('\n')
                if len(lines) >= 2:
                    header = lines[0].split(',')
                    values = lines[1].split(',')
                    for i, key in enumerate(header):
                        if i < len(values) and key == 'bits-per-sense':
                            bits_per_sense = int(values[i])
                            config['mb_per_sense'] = bits_per_sense / (8 * 1024 * 1024)
        
        # Try constellation.dat
        const_path = f"{policy}/constellation.dat"
        if const_path in zipf.namelist():
            with zipf.open(const_path) as f:
                lines = f.read().decode('utf-8').strip().split('\n')
                if len(lines) >= 2:
                    header = lines[0].split(',')
                    values = lines[1].split(',')
                    for i, key in enumerate(header):
                        if i < len(values):
                            if key == 'count':
                                config['satellite_count'] = int(values[i])
                            elif key == 'second':
                                config['frame_spacing'] = float(values[i])
    
    return config

def get_global_time_reference(zip_path):
    """Get global minimum timestamp for consistent time reference"""
    with zipfile.ZipFile(zip_path, 'r') as zipf:
        for policy in POLICIES:
            vis_log_path = f"{policy}/visibility_log.csv"
            if vis_log_path in zipf.namelist():
                with zipf.open(vis_log_path) as f:
                    df = pd.read_csv(f, nrows=100)
                    return df['time'].min()
    return 0.0

def load_buffer_data(zip_path, policy, satellite_id):
    """Load buffer data for a specific satellite"""
    global_min_time = get_global_time_reference(zip_path)
    
    with zipfile.ZipFile(zip_path, 'r') as zipf:
        vis_log_path = f"{policy}/visibility_log.csv"
        with zipf.open(vis_log_path) as f:
            df = pd.read_csv(f)
    
    sat_df = df[df['sat_id'] == satellite_id].sort_values('time').copy()
    
    if len(sat_df) == 0:
        return None
    
    sat_df['hours'] = (sat_df['time'] - global_min_time) / 3600.0
    
    result = pd.DataFrame({
        'hours': sat_df['hours'].values,
        'buffer_mb': sat_df['buffer_mb'].values
    })
    
    return result

def get_all_satellite_totals(zip_path):
    """Get total downloaded MB for all satellites across all policies"""
    all_totals = {}
    
    with zipfile.ZipFile(zip_path, 'r') as zipf:
        for policy in POLICIES:
            vis_log_path = f"{policy}/visibility_log.csv"
            if vis_log_path not in zipf.namelist():
                continue
                
            with zipf.open(vis_log_path) as f:
                df = pd.read_csv(f)
            
            sat_totals = df.groupby('sat_id')['downloaded_mb'].sum()
            
            for sat_id, total in sat_totals.items():
                if sat_id not in all_totals:
                    all_totals[sat_id] = {}
                all_totals[sat_id][policy] = total
    
    return all_totals

def get_orbital_passes(zip_path):
    """Get orbital pass times"""
    global_min_time = get_global_time_reference(zip_path)
    
    with zipfile.ZipFile(zip_path, 'r') as zipf:
        for policy in POLICIES:
            vis_log_path = f"{policy}/visibility_log.csv"
            if vis_log_path not in zipf.namelist():
                continue
                
            with zipf.open(vis_log_path) as f:
                df = pd.read_csv(f)
            
            connected = df[df['connected'] == 1].copy()
            if len(connected) == 0:
                continue
                
            connected['hours'] = (connected['time'] - global_min_time) / 3600.0
            active_times = sorted(connected['hours'].unique())
            
            passes = []
            start, last = None, None
            for time in active_times:
                if last is None or (time - last) > 0.5:
                    if start is not None:
                        passes.append((start, last))
                    start = time
                last = time
            if start is not None:
                passes.append((start, last))
                
            return passes
    
    return []

def create_plot(zip_path, strategy_name, constellation_analysis_folder):
    """Create buffer comparison plot matching original format"""
    
    config = read_config(zip_path, POLICIES[0])
    all_totals = get_all_satellite_totals(zip_path)
    all_satellite_ids = sorted(set(all_totals.keys()))
    passes = get_orbital_passes(zip_path)
    
    if not all_satellite_ids:
        print(f"No satellite data found for {strategy_name}!")
        return
    
    # Create 2x2 subplot layout
    fig, axes = plt.subplots(2, 2, figsize=(28, 24))
    
    # Create title
    title_lines = [f"Satellite Constellation Buffer Analysis - {strategy_name.title()} Strategy"]
    
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
    
    # Generate colors
    policy_colors = plt.cm.tab20(np.linspace(0, 1, 20))
    extra_colors = plt.cm.Set3(np.linspace(0, 1, 20))
    extended_colors = plt.cm.Dark2(np.linspace(0, 1, 10))
    all_colors = list(policy_colors) + list(extra_colors) + list(extended_colors)
    
    for i, policy in enumerate(POLICIES):
        ax = axes[i // 2, i % 2]
        
        # Calculate total
        total_data = 0
        for sat_id in all_totals:
            sat_total = all_totals.get(sat_id, {}).get(policy, 0)
            total_data += sat_total
        
        legend_data = []
        
        # Plot all satellites
        for j, sat_id in enumerate(all_satellite_ids):
            sat_total = all_totals.get(sat_id, {}).get(policy, 0)
            color = all_colors[j % len(all_colors)]
            
            buffer_df = load_buffer_data(zip_path, policy, sat_id)
            if buffer_df is None or sat_total == 0:
                # No data - greyed line at zero
                line = ax.axhline(0, color='lightgray', alpha=0.3, linestyle='--', linewidth=0.5)
                legend_data.append((sat_total, line, f'{sat_id} (0MB)', True))
            else:
                # Plot buffer
                line = ax.plot(buffer_df['hours'], buffer_df['buffer_mb'], 
                       color=color, linewidth=1.5, alpha=0.8, linestyle='solid')[0]
                legend_data.append((sat_total, line, f'{sat_id} ({sat_total:.0f}MB)', False))
        
        # Add orbital passes
        for start, end in passes:
            ax.axvspan(start, end, alpha=0.1, color='green')
        
        # Sort legend
        active_legends = [(data, line, label) for data, line, label, is_grey in legend_data if not is_grey]
        greyed_legends = [(data, line, label) for data, line, label, is_grey in legend_data if is_grey]
        
        active_legends.sort(key=lambda x: x[0], reverse=True)
        greyed_legends.sort(key=lambda x: x[2])
        
        sorted_legends = active_legends + greyed_legends
        
        handles = [item[1] for item in sorted_legends]
        labels = [item[2] for item in sorted_legends]
        
        ax.set_xlabel('Time (hours)')
        ax.set_ylabel('Buffer (MB)')
        ax.set_title(f'{policy.upper()} Scheduling\nTotal Downloaded: {total_data:.0f} MB', fontweight='bold')
        ax.grid(True, alpha=0.3)
        ax.legend(handles, labels, bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=7)
    
    # Save
    output_filename = f"buffer_plot_{strategy_name}_strategy_v2.png"
    output_path = constellation_analysis_folder / output_filename
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"Generated {strategy_name} buffer plot with {len(passes)} orbital passes -> {output_path}")
    return output_path

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Generate satellite buffer level time series plots using visibility_log.csv')
    parser.add_argument('--root-dir', default='.', help='Root directory to search for constellation analysis folders')
    parser.add_argument('--sats', type=int, required=True, help='Number of satellites to filter by')
    parser.add_argument('--image', required=True, help='Image size to filter by (number in MB or alias: s, m, l, xl)')
    
    args = parser.parse_args()
    
    image_size = resolve_image_size(args.image)
    if image_size is None:
        print(f"Error: Invalid image size '{args.image}'. Use a number or alias (s, m, l, xl)")
        return 1
    
    print("Multi-Satellite Buffer Analysis V2")
    print(f"Filtering by: {args.sats} satellites, {image_size:.3f}MB image size")
    
    logs = scan_for_logs(args.root_dir)
    
    if not logs:
        print("No logs found!")
        return 1
    
    available_sats = sorted(set(log['sats'] for log in logs))
    available_images = sorted(set(log['image_size'] for log in logs))
    print(f"Available satellite counts: {available_sats}")
    print(f"Available image sizes: {available_images}")
    
    filtered_logs = [log for log in logs 
                    if log['sats'] == args.sats and abs(log['image_size'] - image_size) < 0.01]
    
    print(f"Found {len(filtered_logs)} logs for sats={args.sats}, image={image_size:.3f}MB")
    
    if not filtered_logs:
        print(f"No matching logs found for {args.sats} satellites and {image_size}MB images")
        return 1
    
    # Group by constellation folder
    constellation_groups = {}
    for log in filtered_logs:
        folder_key = log['constellation_folder']
        if folder_key not in constellation_groups:
            constellation_groups[folder_key] = []
        constellation_groups[folder_key].append(log)
    
    # Process each constellation folder
    generated_plots = []
    for constellation_folder, logs_in_folder in constellation_groups.items():
        print(f"\nProcessing constellation analysis folder: {constellation_folder.name}")
        
        # Group by strategy
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
                zip_path = strategy_logs[0]['simulation_logs_zip']
                output_path = create_plot(zip_path, strategy, constellation_folder)
                if output_path:
                    generated_plots.append(output_path)
            except Exception as e:
                print(f"  Error processing {strategy} strategy: {e}")
    
    if generated_plots:
        print(f"\nBuffer analysis complete! Generated {len(generated_plots)} plots:")
        for plot_path in generated_plots:
            print(f"  {plot_path}")
    else:
        print("No plots were generated.")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
