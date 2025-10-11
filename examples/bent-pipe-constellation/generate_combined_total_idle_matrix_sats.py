#!/usr/bin/env python3
"""Generate combined total idle time matrix (overall system utilization) using visibility logs across all image sizes and satellite counts"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import zipfile
import tempfile
from pathlib import Path
import argparse
import os
import re

def read_config_from_zip(zip_path):
    """Read configuration from simulation_logs.zip"""
    config = {}
    try:
        with zipfile.ZipFile(zip_path, 'r') as zipf:
            # Read sensor configuration - try multiple possible formats
            if 'configuration/sensor.dat' in zipf.namelist():
                with zipf.open('configuration/sensor.dat') as f:
                    content = f.read().decode().strip()
                    lines = content.split('\n')
                    
                    # Try the comma-separated format first
                    if len(lines) >= 2 and ',' in lines[1]:
                        # Format: bits-per-sense,pixel-count,pixel-size-m,focal-length-m,max-buffer-mb
                        data = lines[1].split(',')
                        if len(data) >= 1:
                            # Calculate image size from bits-per-sense
                            bits_per_sense = int(data[0])
                            image_size_mb = bits_per_sense / (8 * 1024 * 1024)  # Convert bits to MB
                            config['image_size'] = image_size_mb
                    else:
                        # Try the space-separated format
                        for line in lines:
                            if line.startswith('sensor-image-size-MB'):
                                config['image_size'] = float(line.split()[-1])
    except Exception as e:
        print(f"Warning: Could not read config from zip: {e}")
        config['image_size'] = 0.289  # Default fallback
    
    return config

def calculate_total_idle_from_visibility_log(policy_dir):
    """Calculate total idle time from visibility_log.csv using efficient event-based approach"""
    
    visibility_log_path = policy_dir / "visibility_log.csv"
    
    if not visibility_log_path.exists():
        print(f"   ⚠️  No visibility log found")
        return 0, 0
    
    try:
        # Read visibility log
        df = pd.read_csv(visibility_log_path)
        
        if len(df) == 0:
            return 0, 0
        
        # Get simulation time span from simulation_summary.txt or default to 6 hours
        sim_duration = 21600  # 6 hours in seconds - this is the total simulation time
        
        # For total idle calculation: time when system could be productive but isn't
        # Total idle = (simulation time - time when connected AND buffer > threshold) / simulation time
        # This includes:
        # 1. Unconnected time (no satellite connected)
        # 2. Connected but empty buffer time (satellite connected but buffer <= 0.001 MB)
        
        # Count events when system is productively active: connected AND buffer > threshold
        productive_events = df[(df['connected'] == 1) & (df['buffer_mb'] > 0.001)]
        
        # Since we confirmed only 1 satellite connects at a time, each event = 1 second
        # For scalability to multi-GS: this counts total productive seconds across all connections
        actual_productive_time = len(productive_events)
        
        # Total idle time = simulation duration - productive time
        total_idle_time = sim_duration - actual_productive_time
        
        return total_idle_time, sim_duration
        
    except Exception as e:
        print(f"   Error processing visibility log: {e}")
        return 0, 0

def calculate_total_idle_for_strategy(strategy_folder):
    """Calculate total idle time percentages and absolute counts for all policies in a strategy using visibility logs"""
    policies = ["sticky", "roundrobin", "fifo", "random"]
    results = {}
    idle_data = {}
    
    simulation_logs_zip = strategy_folder / "simulation_logs.zip"
    
    if not simulation_logs_zip.exists():
        print(f"   ❌ No simulation logs found")
        return {policy: 0 for policy in policies}, {policy: 0 for policy in policies}
    
    # Read configuration for image size
    config = read_config_from_zip(simulation_logs_zip)
    image_size = config.get('image_size', 0.289)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        with zipfile.ZipFile(simulation_logs_zip, 'r') as zipf:
            zipf.extractall(temp_path)
        
        for policy in policies:
            policy_dir = temp_path / policy
            
            if policy_dir.exists():
                # Calculate total idle time using efficient visibility log approach
                total_idle_time, sim_duration = calculate_total_idle_from_visibility_log(policy_dir)
                
                # Calculate idle percentage based on total simulation time
                if sim_duration > 0:
                    idle_percentage = (total_idle_time / sim_duration) * 100
                else:
                    idle_percentage = 100  # If no simulation time, assume 100% idle
                
                results[policy] = idle_percentage
                idle_data[policy] = total_idle_time  # Store absolute idle time in seconds
                
                print(f"   {policy}: {sim_duration - total_idle_time}/{sim_duration}s productive time = {idle_percentage:.1f}% total idle")
            else:
                results[policy] = 0
                idle_data[policy] = 0
    
    return results, idle_data

def extract_image_size_from_folder(folder_name):
    """Extract image size from folder name like constellation_analysis_20251007_193320_28000_50"""
    # New format: constellation_analysis_YYYYMMDD_HHMMSS_IMAGESIZE_SATCOUNT
    # Extract the second-to-last number (image size), not the last (satellite count)
    match = re.search(r'_(\d+)_\d+$', folder_name)
    if match:
        size_str = match.group(1)
        # Convert to MB - add decimal point in appropriate position
        if len(size_str) == 5:  # 00028 -> 0.028, 28000 -> 28.000
            if size_str.startswith('000'):  # 00028 -> 0.028
                return float(size_str) / 1000
            else:  # 28000 -> 28.0
                return float(size_str) / 1000
        elif len(size_str) == 4:  # 0280 -> 0.280, 2800 -> 2.800
            return float(size_str) / 1000
        else:
            return float(size_str) / 1000
    return None

def extract_satellite_count_from_folder(folder_name):
    """Extract satellite count from folder name like constellation_analysis_20251007_193320_28000_50"""
    # New format: constellation_analysis_YYYYMMDD_HHMMSS_IMAGESIZE_SATCOUNT
    # Extract the last number (satellite count)
    match = re.search(r'_(\d+)$', folder_name)
    if match:
        return int(match.group(1))
    return 1  # fallback

def extract_params_from_folder(folder_name):
    """Extract both image size and satellite count from folder name"""
    image_size = extract_image_size_from_folder(folder_name)
    satellite_count = extract_satellite_count_from_folder(folder_name)
    return image_size, satellite_count

def generate_combined_idle_matrix_sats(base_folder):
    """Generate combined 4D idle time matrix for all image sizes, satellite counts and strategies"""
    base_path = Path(base_folder)
    
    if not base_path.exists():
        print(f"❌ Base folder not found: {base_folder}")
        return
    
    print(f"=== Generating Combined 4D Idle Time Matrix ===")
    print(f"📁 Base folder: {base_folder}")
    
    # Find all analysis folders
    analysis_folders = [f for f in base_path.iterdir() 
                       if f.is_dir() and f.name.startswith('constellation_analysis_')]
    
    if not analysis_folders:
        print(f"❌ No analysis folders found")
        return
    
    # Group folders by image size and satellite count
    param_groups = {}
    for folder in analysis_folders:
        img_size, sat_count = extract_params_from_folder(folder.name)
        if img_size is not None and sat_count is not None:
            if img_size not in param_groups:
                param_groups[img_size] = {}
            param_groups[img_size][sat_count] = folder
    
    # Sort parameters for consistent ordering
    image_sizes = sorted(param_groups.keys())
    satellite_counts = sorted(set(sc for img_data in param_groups.values() for sc in img_data.keys()))
    
    print(f"Found data for:")
    print(f"  📷 Image sizes: {[f'{size:.3f} MB' for size in image_sizes]}")
    print(f"  🛰️  Satellite counts: {satellite_counts}")
    print(f"  📊 Total combinations: {len(image_sizes)} × {len(satellite_counts)} = {len(image_sizes) * len(satellite_counts)}")
    
    strategies = ["close-spaced", "frame-spaced", "orbit-spaced", "close-orbit-spaced"]
    policies = ["sticky", "roundrobin", "fifo", "random"]
    
    # Calculate idle data for each parameter combination
    all_idle_data = {}
    all_timestep_data = {}
    
    for img_size in image_sizes:
        all_idle_data[img_size] = {}
        all_timestep_data[img_size] = {}
        
        for sat_count in satellite_counts:
            if sat_count in param_groups[img_size]:
                analysis_folder = param_groups[img_size][sat_count]
                print(f"\n🔄 Processing {img_size:.3f} MB, {sat_count} sats...")
                
                idle_data = {}
                timestep_data = {}
                
                for strategy in strategies:
                    strategy_folder = analysis_folder / strategy
                    
                    if strategy_folder.exists():
                        idle_data[strategy], timestep_data[strategy] = calculate_total_idle_for_strategy(strategy_folder)
                        print(f"   ✅ {strategy}: Processed")
                    else:
                        print(f"   ❌ {strategy}: Not found")
                        idle_data[strategy] = {policy: 0 for policy in policies}
                        timestep_data[strategy] = {policy: 0 for policy in policies}
                
                all_idle_data[img_size][sat_count] = idle_data
                all_timestep_data[img_size][sat_count] = timestep_data
            else:
                print(f"\n⚠️  Missing data for {img_size:.3f} MB, {sat_count} sats")
                # Fill with zeros for missing combinations
                all_idle_data[img_size][sat_count] = {
                    strategy: {policy: 0 for policy in policies} 
                    for strategy in strategies
                }
                all_timestep_data[img_size][sat_count] = {
                    strategy: {policy: 0 for policy in policies} 
                    for strategy in strategies
                }
    
    if not image_sizes or not satellite_counts:
        print("❌ No valid data found!")
        return

    # Create 4D matrix: each "big cell" (policy×strategy) is subdivided into:
    # - 4 rows (image sizes) × 4 columns (satellite counts) = 16 sub-cells
    rows_per_policy = len(image_sizes)  # 4 image sizes per policy
    cols_per_strategy = len(satellite_counts)  # 4 satellite counts per strategy
    total_rows = len(policies) * rows_per_policy
    total_cols = len(strategies) * cols_per_strategy

    idle_matrix = np.zeros((total_rows, total_cols))
    timestep_matrix = np.zeros((total_rows, total_cols))

    # Fill the matrix: each policy×strategy combination gets a 4×4 sub-matrix
    for policy_idx, policy in enumerate(policies):
        for img_idx, img_size in enumerate(image_sizes):
            row_idx = policy_idx * rows_per_policy + img_idx
            
            for strategy_idx, strategy in enumerate(strategies):
                for sat_count_idx, sat_count in enumerate(satellite_counts):
                    col_idx = strategy_idx * cols_per_strategy + sat_count_idx
                    
                    # Access the idle percentage from the 4D data structure
                    if (img_size in all_idle_data and 
                        sat_count in all_idle_data[img_size] and 
                        strategy in all_idle_data[img_size][sat_count] and 
                        policy in all_idle_data[img_size][sat_count][strategy]):
                        
                        idle_percentage = all_idle_data[img_size][sat_count][strategy][policy]
                        timestep_count = all_timestep_data[img_size][sat_count][strategy][policy]
                    else:
                        idle_percentage = 0
                        timestep_count = 0
                    
                    idle_matrix[row_idx, col_idx] = idle_percentage
                    timestep_matrix[row_idx, col_idx] = timestep_count

    # Create large figure for 4D matrix
    fig, ax = plt.subplots(figsize=(24, 18))
    
    # Use Reds colormap (higher total idle time = worse = darker red)
    cmap = 'Reds'
    
    # Create the heatmap based on total idle timesteps (not percentage)
    im = ax.imshow(timestep_matrix, cmap=cmap, aspect='auto')
    
    # Improved x-axis labels: Satellite counts on top, strategy names below (like y-axis structure)
    # X-axis configuration: satellite counts on top, strategy names centered at bottom
    x_positions = []
    x_labels_top = []
    strategy_positions = []
    strategy_labels = []
    
    for strategy_idx, strategy in enumerate(strategies):
        # Calculate center position for strategy label
        strategy_start_col = strategy_idx * cols_per_strategy
        strategy_center_col = strategy_start_col + (cols_per_strategy - 1) / 2
        strategy_positions.append(strategy_center_col)
        strategy_labels.append(strategy.replace('-', ' ').title())
        
        for sat_count_idx, sat_count in enumerate(satellite_counts):
            col_idx = strategy_idx * cols_per_strategy + sat_count_idx
            x_positions.append(col_idx)
            x_labels_top.append(str(sat_count))
    
    # Set main x-axis labels (satellite counts)
    ax.set_xticks(x_positions)
    ax.set_xticklabels(x_labels_top, fontsize=12, fontweight='bold')
    
    # Create secondary x-axis at bottom for centered strategy names
    ax3 = ax.secondary_xaxis('bottom')
    ax3.set_xticks(strategy_positions)
    ax3.set_xticklabels(strategy_labels, fontsize=14, fontweight='bold')
    ax3.tick_params(axis='x', which='major', pad=20)
    
    # Y-axis labels: Policies centered vertically with image sizes
    all_y_positions = []
    all_y_labels = []
    
    for policy_idx, policy in enumerate(policies):
        # Calculate the middle position for this policy group
        policy_start_row = policy_idx * rows_per_policy
        policy_middle_row = policy_start_row + (rows_per_policy - 1) / 2
        
        for img_idx, img_size in enumerate(image_sizes):
            row_idx = policy_idx * rows_per_policy + img_idx
            all_y_positions.append(row_idx)
            
            # Format size label
            if img_size < 1:
                size_label = f".{int(img_size * 1000):03d}"  # .028, .289
            else:
                size_label = f"{img_size:.0f}"  # 3, 29
            
            # Show policy name only at the vertical center of the policy group
            if img_idx == len(image_sizes) // 2:  # Middle position
                label = f"{policy.upper()}  {size_label}"
            else:
                label = f"      {size_label}"  # Indent image sizes
            
            all_y_labels.append(label)
    
    ax.set_yticks(all_y_positions)
    ax.set_yticklabels(all_y_labels, fontsize=12, fontweight='bold')
    
    # Add separator lines between strategies
    for strategy_idx in range(1, len(strategies)):
        x_pos = strategy_idx * cols_per_strategy - 0.5
        ax.axvline(x=x_pos, color='black', linewidth=2)
    
    # Add separator lines between policies
    for policy_idx in range(1, len(policies)):
        y_pos = policy_idx * rows_per_policy - 0.5
        ax.axhline(y=y_pos, color='black', linewidth=2)
    
    # Add colorbar
    cbar = plt.colorbar(im, ax=ax, shrink=0.6)
    cbar.set_label('Total Idle Time (%)', rotation=270, labelpad=25, fontsize=14, fontweight='bold')
    cbar.ax.tick_params(labelsize=10)
    
    # Add text annotations with values - show idle time and percentage
    for policy_idx, policy in enumerate(policies):
        for img_idx, img_size in enumerate(image_sizes):
            row_idx = policy_idx * rows_per_policy + img_idx
            
            for strategy_idx, strategy in enumerate(strategies):
                for sat_count_idx, sat_count in enumerate(satellite_counts):
                    col_idx = strategy_idx * cols_per_strategy + sat_count_idx
                    idle_seconds = timestep_matrix[row_idx, col_idx]
                    productive_seconds = 21600 - idle_seconds  # Productive time = total - idle
                    idle_pct = idle_matrix[row_idx, col_idx]
                    
                    # Format text showing productive/total time and idle percentage
                    value_text = f'{int(productive_seconds)}/21600s\n{idle_pct:.1f}%'
                        
                    text = ax.text(col_idx, row_idx, value_text, ha="center", va="center", 
                                 color='black', fontweight='bold', fontsize=10)
    
    # Create simplified title
    title = f'Total Idle Time (Productive Time / Total Simulation Time)'
    
    # Titles and labels
    ax.set_title(title, fontsize=18, fontweight='bold', pad=40)
    ax.set_xlabel('Satellite Count', fontsize=14, fontweight='bold')
    ax.set_ylabel('Scheduling Policy & Image Size', fontsize=14, fontweight='bold')
    
    # Add grid for better readability
    ax.set_xticks(np.arange(total_cols+1)-.5, minor=True)
    ax.set_yticks(np.arange(total_rows+1)-.5, minor=True)
    ax.grid(which="minor", color="gray", linestyle='-', linewidth=0.5)
    ax.tick_params(which="minor", size=0)
    
    plt.tight_layout()
    
    # Save the plot to current working directory
    if base_path.name == ".":
        output_path = Path.cwd() / 'combined_total_idle_matrix_sats.png'
    else:
        output_path = base_path / 'combined_total_idle_matrix_sats.png'
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"\n✅ Combined 4D total idle matrix saved: {output_path}")
    
    # Save the raw data with proper 4D structure
    # Print summary showing worst idle performance for each policy across all image sizes
    print(f"\n=== COMBINED TOTAL IDLE TIME SUMMARY ===")
    print(f"{'Policy':<15} {'Image Size':<12} {'Worst Strategy':<25} {'Worst Sat Count':<15} {'Idle Time (s)':<15} {'Idle %':<12}")
    print("-" * 110)
    
    for policy_idx, policy in enumerate(policies):
        for img_idx, img_size in enumerate(image_sizes):
            row_idx = policy_idx * rows_per_policy + img_idx
            row_idles = idle_matrix[row_idx, :]
            worst_col_idx = np.argmax(row_idles)  # Highest idle = worst
            
            # Convert flat column index back to strategy and satellite count
            worst_strategy_idx = worst_col_idx // len(satellite_counts)
            worst_sat_count_idx = worst_col_idx % len(satellite_counts)
            worst_strategy = strategies[worst_strategy_idx]
            worst_sat_count = satellite_counts[worst_sat_count_idx]
            worst_idle = row_idles[worst_col_idx]
            worst_seconds = timestep_matrix[row_idx, worst_col_idx]
            
            print(f"{policy.upper():<15} {img_size:>7.3f} MB   {worst_strategy:<25} {worst_sat_count:>10} sat    {int(worst_seconds):>10}      {worst_idle:>8.1f}%")

def main():
    parser = argparse.ArgumentParser(description='Generate combined 4D total idle time matrix across image sizes and satellite counts using visibility logs')
    parser.add_argument('base_folder', help='Path to folder containing multiple analysis folders')
    args = parser.parse_args()
    
    generate_combined_idle_matrix_sats(args.base_folder)

if __name__ == "__main__":
    main()