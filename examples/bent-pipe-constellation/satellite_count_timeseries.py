#!/usr/bin/env python3
"""
Satellite Count Timeseries

Simple aggregate plot showing total number of satellites in view over time.
Single line per policy showing contention level at each moment.
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
import shutil

# Configuration - use absolute paths
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
        target_clean = target.lower().replace('-', '').replace(' ', '')
        name_clean = clean_name.lower().replace('-', '').replace(' ', '')
        if target_clean == name_clean:
            return target
    return None

def parse_folder_path(path):
    """Parse folder path to extract sats, image_size"""
    path_str = str(path)
    constellation_match = re.search(r'constellation_analysis_\d+_\d+_(\d+)_(\d+)', path_str)
    if constellation_match:
        image_size_str = constellation_match.group(1)
        sat_count_str = constellation_match.group(2)
        try:
            image_size = float(image_size_str) / 1000.0
            sat_count = int(sat_count_str)
            return {'sats': sat_count, 'image_size': image_size}
        except (ValueError, IndexError):
            pass
    return None

def discover_logs(root_dir="."):
    """Discover all simulation logs and extract metadata"""
    root_path = Path(root_dir)
    logs = []
    
    print(f"Searching for visibility logs in: {root_path.absolute()}")
    
    constellation_folders = list(root_path.glob('constellation_analysis_*'))
    
    for constellation_folder in constellation_folders:
        constellation_meta = parse_folder_path(constellation_folder)
        if not constellation_meta:
            continue
            
        for strategy in STRATEGIES:
            strategy_folder = constellation_folder / strategy
            if not strategy_folder.exists():
                continue
                
            zip_path = strategy_folder / "simulation_logs.zip"
            if not zip_path.exists():
                continue
            
            try:
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    for policy in POLICIES:
                        vis_log_path = f"{policy}/visibility_log.csv"
                        if vis_log_path in zf.namelist():
                            log_entry = {
                                'path': zip_path,
                                'strategy': strategy,
                                'policy': policy,
                                'sats': constellation_meta['sats'],
                                'image_size': constellation_meta['image_size'],
                                'constellation_folder': constellation_folder
                            }
                            logs.append(log_entry)
            except Exception as e:
                print(f"  Warning: Could not read {zip_path}: {e}")
                continue
    
    return logs

def calculate_satellite_count_timeseries(zip_path, policy):
    """
    Calculate aggregate count of satellites in view over time.
    Returns dict with 'hours' and 'count' arrays.
    """
    temp_dir = tempfile.mkdtemp()
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            vis_log_path = f"{policy}/visibility_log.csv"
            if vis_log_path not in zf.namelist():
                print(f"    Warning: No visibility_log.csv found for {policy}")
                return None
            zf.extract(vis_log_path, temp_dir)
        
        vis_log_file = Path(temp_dir) / policy / "visibility_log.csv"
        
        if not vis_log_file.exists():
            return None
        
        # Read visibility log
        df = pd.read_csv(vis_log_file)
        
        if len(df) == 0:
            return None
        
        # At each time snapshot, count how many satellites are in_view across all sats
        # Only count rows where in_view=1
        in_view_df = df[df['in_view'] == 1]
        count_per_time = in_view_df.groupby('time').size().reset_index(name='count')
        
        # Get all unique times to ensure we have zero counts when no satellites are in view
        all_times = pd.DataFrame({'time': sorted(df['time'].unique())})
        count_per_time = all_times.merge(count_per_time, on='time', how='left')
        count_per_time['count'] = count_per_time['count'].fillna(0).astype(int)
        
        # Detect and smooth rapid oscillations (e.g., 50->1->50->1 flicker at 10° threshold)
        # If we see the count rapidly alternating between two values, take the max
        count_per_time['smoothed'] = count_per_time['count'].copy()
        
        window_size = 5  # Look at 5 consecutive samples
        for i in range(len(count_per_time) - window_size + 1):
            window = count_per_time.iloc[i:i+window_size]['count'].values
            unique_vals = set(window)
            
            # If we see only 2 unique values alternating, it's likely flicker
            if len(unique_vals) == 2:
                # Take the maximum value in this window
                max_val = max(unique_vals)
                # Apply to middle of window
                count_per_time.loc[i+2, 'smoothed'] = max_val
        
        # Only keep points where smoothed count changes
        changes = []
        changes.append(0)  # Always keep first point
        
        for i in range(1, len(count_per_time)):
            prev_count = count_per_time.iloc[changes[-1]]['smoothed']
            curr_count = count_per_time.iloc[i]['smoothed']
            
            # Keep this point if count changed
            if curr_count != prev_count:
                changes.append(i)
        
        # Always keep last point
        if changes[-1] != len(count_per_time) - 1:
            changes.append(len(count_per_time) - 1)
        
        # Filter to only changed points
        count_changes = count_per_time.iloc[changes].copy()
        
        # Convert time to hours
        count_changes['hours'] = count_changes['time'] / 3600.0
        
        return {
            'hours': count_changes['hours'].values,
            'count': count_changes['smoothed'].values
        }
        
    finally:
        try:
            shutil.rmtree(temp_dir)
        except:
            pass

def plot_satellite_count_timeseries(spacing_data, output_path, num_sats, image_size):
    """
    Generate 2x2 subplot for all spacing strategies showing satellite count over time.
    Single line per spacing strategy (contention is independent of link policy).
    """
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    axes = axes.flatten()
    
    fig.suptitle(f'Satellites in View Over Time (Contention)\n'
                 f'{num_sats} satellites, {image_size:.3f} MB image size',
                 fontsize=14, fontweight='bold', y=0.995)
    
    for idx, spacing in enumerate(STRATEGIES):
        ax = axes[idx]
        
        if spacing not in spacing_data or spacing_data[spacing] is None:
            ax.text(0.5, 0.5, 'No Data', ha='center', va='center', fontsize=14)
            ax.set_title(f'{spacing}')
            continue
        
        data = spacing_data[spacing]
        hours = data['hours']
        count = data['count']
        
        # Plot as step chart - horizontal lines with vertical jumps at changes
        # This prevents diagonal lines that create "bar" appearance with many transitions
        ax.plot(hours, count, linewidth=0.5, color='#2E86AB', alpha=1.0, drawstyle='steps-post')
        
        ax.set_title(f'{spacing}',
                    fontsize=12, fontweight='bold')
        ax.set_xlabel('Time (hours)', fontsize=10)
        ax.set_ylabel('Satellites in View', fontsize=10)
        ax.grid(True, alpha=0.3)
        
        # Set y-axis to show from 0 to max satellites
        max_count = int(count.max()) if len(count) > 0 else num_sats
        ax.set_ylim(0, max_count + 5)
    
    plt.tight_layout()
    
    # Save the plot
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    
    print(f"  ✅ Saved: {output_path}")
    return True

def main():
    parser = argparse.ArgumentParser(
        description='Generate satellite count timeseries showing total satellites in view over time'
    )
    parser.add_argument('--image', type=str, 
                       help='Image size (s/m/l/xl or numeric MB value)')
    parser.add_argument('--sats', type=int,
                       help='Number of satellites')
    parser.add_argument('--policy', type=str,
                       help='Policy name (sticky, fifo, roundrobin, random)')
    parser.add_argument('--spacing', type=str,
                       help='Spacing strategy (close-spaced, orbit-spaced, etc)')
    
    args = parser.parse_args()
    
    # Discover all available logs
    all_logs = discover_logs(SCRIPT_DIR)
    
    if not all_logs:
        print("❌ No visibility logs found!")
        return 1
    
    # Filter logs based on arguments
    filtered_logs = all_logs
    
    if args.image:
        if args.image.lower() in IMAGE_ALIASES:
            target_image = IMAGE_ALIASES[args.image.lower()]
        else:
            try:
                target_image = float(args.image)
            except ValueError:
                print(f"❌ Invalid image size: {args.image}")
                return 1
        filtered_logs = [log for log in filtered_logs 
                        if abs(log['image_size'] - target_image) < 0.001]
    
    if args.sats:
        filtered_logs = [log for log in filtered_logs 
                        if log['sats'] == args.sats]
    
    if args.policy:
        target_policy = normalize_name(args.policy, POLICIES)
        if target_policy:
            filtered_logs = [log for log in filtered_logs 
                           if log['policy'] == target_policy]
    
    if args.spacing:
        target_spacing = normalize_name(args.spacing, STRATEGIES)
        if target_spacing:
            filtered_logs = [log for log in filtered_logs 
                           if log['strategy'] == target_spacing]
    
    if not filtered_logs:
        print("❌ No logs match the specified filters!")
        return 1
    
    # Group by spacing strategy
    by_spacing = {}
    for log in filtered_logs:
        spacing = log['strategy']
        if spacing not in by_spacing:
            by_spacing[spacing] = []
        by_spacing[spacing].append(log)
    
    # Group by constellation (image_size + sats)
    by_constellation = {}
    for log in filtered_logs:
        key = (log['image_size'], log['sats'], log['constellation_folder'])
        if key not in by_constellation:
            by_constellation[key] = []
        by_constellation[key].append(log)
    
    print(f"📁 Found {len(by_constellation)} constellation(s) to process\n")
    
    # Process each constellation
    for (image_size, sats, constellation_folder), logs in sorted(by_constellation.items()):
        print(f"📊 Generating satellite count timeseries for {sats} sats, {image_size:.3f} MB...")
        
        # Group by spacing strategy (use first policy since contention is policy-independent)
        spacing_data = {}
        
        # Get unique spacing strategies
        spacings = set(log['strategy'] for log in logs)
        
        for spacing in sorted(spacings):
            # Find any log for this spacing (just need one policy since they all see same satellites)
            spacing_logs = [log for log in logs if log['strategy'] == spacing]
            if spacing_logs:
                log = spacing_logs[0]  # Use first policy found
                policy = log['policy']
                
                print(f"  Processing {spacing} (using {policy} policy as reference)...")
                
                # Calculate satellite count timeseries
                timeseries = calculate_satellite_count_timeseries(log['path'], policy)
                
                if timeseries:
                    print(f"    Max satellites in view: {int(timeseries['count'].max())}")
                    print(f"    Avg satellites in view: {timeseries['count'].mean():.1f}")
                
                spacing_data[spacing] = timeseries
        
        # Generate single plot with all spacing strategies
        if any(v is not None for v in spacing_data.values()):
            # Format image size for filename
            if image_size < 0.1:
                image_str = f"0p0{int(image_size * 1000)}MB"
            elif image_size < 1:
                image_str = f"0p{int(image_size * 1000)}MB"
            else:
                image_str = f"{int(image_size)}MB"
            
            output_filename = f"satellite_count_timeseries_{image_str}_{sats}sats.png"
            output_path = constellation_folder / output_filename
            
            # Create data directory for CSV exports
            data_dir = constellation_folder / f"satellite_count_timeseries_{image_str}_{sats}sats_data"
            data_dir.mkdir(exist_ok=True)
            
            # Export CSV for each spacing strategy
            for spacing, data in spacing_data.items():
                if data is not None:
                    csv_path = data_dir / f"{spacing}.csv"
                    df = pd.DataFrame({
                        'time_hours': data['hours'],
                        'satellites_in_view': data['count']
                    })
                    df.to_csv(csv_path, index=False)
                    print(f"  ✅ Saved CSV: {csv_path}")
            
            plot_satellite_count_timeseries(spacing_data, output_path, sats, image_size)
    
    print("✅ All satellite count timeseries plots generated!")
    return 0

if __name__ == '__main__':
    sys.exit(main())
