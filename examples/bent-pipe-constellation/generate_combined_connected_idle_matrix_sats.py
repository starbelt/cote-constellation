#!/usr/bin/env python3
"""Generate combined connected idle time matrix (satellites wasting link time) using visibility logs across all image sizes and satellite counts"""

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

def calculate_connected_idle_from_visibility_log(policy_dir):
    """Calculate connected idle time from visibility_log.csv using efficient event-based approach"""
    
    visibility_log_path = policy_dir / "visibility_log.csv"
    
    if not visibility_log_path.exists():
        return 0, 0, 0
    
    try:
        # Read visibility log
        df = pd.read_csv(visibility_log_path)
        
        if len(df) == 0:
            return 0, 0, 0
        
        # Calculate connected idle events: connected=1 AND buffer_mb <= 0.001
        connected_idle_events = df[(df['connected'] == 1) & (df['buffer_mb'] <= 0.001)]
        
        # Count total connection events for percentage calculation
        total_connected_events = df[df['connected'] == 1]
        
        if len(total_connected_events) > 0:
            connected_idle_percentage = (len(connected_idle_events) / len(total_connected_events)) * 100
        else:
            connected_idle_percentage = 0
        
        return connected_idle_percentage, len(connected_idle_events), len(total_connected_events)
        
    except Exception as e:
        print(f"Error processing visibility log: {e}")
        return 0, 0, 0

def calculate_connected_idle_for_strategy(strategy_folder):
    """Calculate connected idle time percentages and absolute counts for all policies in a strategy using visibility logs"""
    
    policies = ["sticky", "roundrobin", "fifo", "random"]
    results = {}
    idle_counts = {}
    total_counts = {}
    
    simulation_logs_zip = strategy_folder / "simulation_logs.zip"
    
    if not simulation_logs_zip.exists():
        return {policy: 0 for policy in policies}, {policy: 0 for policy in policies}, {policy: 0 for policy in policies}
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        try:
            with zipfile.ZipFile(simulation_logs_zip, 'r') as zipf:
                zipf.extractall(temp_path)
        except Exception as e:
            print(f"Error extracting {simulation_logs_zip}: {e}")
            return {policy: 0 for policy in policies}, {policy: 0 for policy in policies}, {policy: 0 for policy in policies}
        
        for policy in policies:
            policy_dir = temp_path / policy
            
            if policy_dir.exists():
                # Calculate connected idle time using efficient visibility log approach
                idle_percentage, idle_count, total_count = calculate_connected_idle_from_visibility_log(policy_dir)
                results[policy] = idle_percentage
                idle_counts[policy] = idle_count
                total_counts[policy] = total_count
            else:
                results[policy] = 0
                idle_counts[policy] = 0
                total_counts[policy] = 0
    
    return results, idle_counts, total_counts

def extract_params_from_folder(folder_name):
    """Extract satellite count and image size from constellation analysis folder name"""
    # Pattern: constellation_analysis_YYYYMMDD_HHMMSS_IMAGESIZE_SATCOUNT
    parts = folder_name.split('_')
    if len(parts) >= 6:
        try:
            # Image size (5-digit format like 00027, 00279, 02799, 28000)
            size_str = parts[4]
            image_size = float(size_str) / 1000.0  # Convert to MB
            
            # Satellite count
            sat_count = int(parts[5])
            
            return image_size, sat_count
        except (ValueError, IndexError):
            pass
    
    return None, None

def generate_combined_connected_idle_matrix_4d(base_folder):
    """Generate 4D connected idle matrix across all image sizes and satellite counts"""
    base_path = Path(base_folder)
    
    if not base_path.exists():
        print(f"❌ Base folder not found: {base_folder}")
        return
    
    print(f"=== Generating 4D Connected Idle Matrix ===")
    print(f"📁 Base folder: {base_folder}")
    
    # Find all constellation analysis folders
    analysis_folders = [
        f for f in base_path.iterdir() 
        if f.is_dir() and f.name.startswith('constellation_analysis_')
    ]
    
    if not analysis_folders:
        print(f"❌ No constellation analysis folders found")
        return
    
    # Extract parameters and group by image size and satellite count
    folder_data = {}
    image_sizes = set()
    satellite_counts = set()
    
    for folder in analysis_folders:
        image_size, sat_count = extract_params_from_folder(folder.name)
        if image_size is not None and sat_count is not None:
            folder_data[(image_size, sat_count)] = folder
            image_sizes.add(image_size)
            satellite_counts.add(sat_count)
    
    if not folder_data:
        print(f"❌ No valid constellation analysis folders found")
        return
    
    # Sort parameters
    image_sizes = sorted(image_sizes)
    satellite_counts = sorted(satellite_counts)
    strategies = ["close-spaced", "frame-spaced", "orbit-spaced", "close-orbit-spaced"]
    policies = ["sticky", "roundrobin", "fifo", "random"]
    
    print(f"📊 Found {len(folder_data)} parameter combinations:")
    print(f"   Image sizes: {[f'{s:.3f}MB' for s in image_sizes]}")
    print(f"   Satellite counts: {satellite_counts}")
    
    # Enhanced progress output
    print(f"Found data for:")
    print(f"  📷 Image sizes: {[f'{s:.3f} MB' for s in image_sizes]}")
    print(f"  🛰️  Satellite counts: {satellite_counts}")
    print(f"  📊 Total combinations: {len(image_sizes)} × {len(satellite_counts)} = {len(image_sizes) * len(satellite_counts)}")
    
    # Initialize data structures for 4D matrix
    rows_per_policy = len(image_sizes)
    cols_per_strategy = len(satellite_counts)
    total_rows = len(policies) * rows_per_policy
    total_cols = len(strategies) * cols_per_strategy
    
    # Create matrices to store total counts for each cell
    idle_matrix = np.zeros((total_rows, total_cols))
    counts_matrix = np.zeros((total_rows, total_cols))
    total_matrix = np.zeros((total_rows, total_cols))  # Store total connected events
    
    # Fill matrices with enhanced progress output
    for img_size in image_sizes:
        for sat_count in satellite_counts:
            # Get folder for this parameter combination
            folder = folder_data.get((img_size, sat_count))
            if folder is None:
                print(f"\n⚠️  Missing data for {img_size:.3f} MB, {sat_count} sats")
                continue
                
            print(f"\n🔄 Processing {img_size:.3f} MB, {sat_count} sats...")
            
            for strategy_idx, strategy in enumerate(strategies):
                strategy_folder = folder / strategy
                if not strategy_folder.exists():
                    print(f"   ❌ {strategy}: Not found")
                    continue
                
                # Calculate connected idle for this strategy
                idle_percentages, idle_counts, total_counts = calculate_connected_idle_for_strategy(strategy_folder)
                
                # Show detailed progress for each policy
                for policy in policies:
                    idle_pct = idle_percentages[policy]
                    idle_count = idle_counts[policy]
                    total_count = total_counts[policy]
                    active_count = total_count - idle_count
                    # Show format: "active_events/total_connected_events active connected events = X% connected idle"
                    print(f"   {policy}: {int(active_count)}/{int(total_count)} active connected events = {idle_pct:.1f}% connected idle")
                
                print(f"   ✅ {strategy}: Processed")
                
                # Fill matrix positions for all policies and image sizes
                for policy_idx, policy in enumerate(policies):
                    img_idx = image_sizes.index(img_size)
                    sat_count_idx = satellite_counts.index(sat_count)
                    
                    row_idx = policy_idx * rows_per_policy + img_idx
                    col_idx = strategy_idx * cols_per_strategy + sat_count_idx
                    
                    idle_matrix[row_idx, col_idx] = idle_percentages[policy]
                    counts_matrix[row_idx, col_idx] = idle_counts[policy]
                    total_matrix[row_idx, col_idx] = total_counts[policy]  # Store total connected events
    
    # Create visualization with larger figure size for better readability
    plt.figure(figsize=(20, 14))
    ax = plt.gca()
    
    # Use Reds colormap (higher connected idle = worse = darker red)
    im = ax.imshow(idle_matrix, cmap='Reds', aspect='auto', vmin=0, vmax=100)
    
    # Create the heatmap based on connected idle percentages
    ax.set_xticks(range(total_cols))
    ax.set_yticks(range(total_rows))
    
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
    
    # Set main x-axis labels (satellite counts) with larger font
    ax.set_xticks(x_positions)
    ax.set_xticklabels(x_labels_top, fontsize=12, fontweight='bold')
    
    # Create secondary x-axis at bottom for centered strategy names with larger font
    ax3 = ax.secondary_xaxis('bottom')
    ax3.set_xticks(strategy_positions)
    ax3.set_xticklabels(strategy_labels, fontsize=14, fontweight='bold')
    ax3.tick_params(axis='x', which='major', pad=25)
    
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
    
    # Add colorbar with larger font
    cbar = plt.colorbar(im, ax=ax, shrink=0.7)
    cbar.set_label('Connected Idle Time (%)', rotation=270, labelpad=25, fontsize=14, fontweight='bold')
    cbar.ax.tick_params(labelsize=12)
    
    # Add text annotations with values using pre-calculated data
    for policy_idx, policy in enumerate(policies):
        for img_idx, img_size in enumerate(image_sizes):
            for strategy_idx, strategy in enumerate(strategies):
                for sat_count_idx, sat_count in enumerate(satellite_counts):
                    row_idx = policy_idx * rows_per_policy + img_idx
                    col_idx = strategy_idx * cols_per_strategy + sat_count_idx
                    
                    idle_count = counts_matrix[row_idx, col_idx]
                    idle_pct = idle_matrix[row_idx, col_idx]
                    total_connected = total_matrix[row_idx, col_idx]
                    active_connected = total_connected - idle_count
                    
                    # Format text showing active/total connected events and idle percentage
                    value_text = f'{int(active_connected)}/{int(total_connected)}\n{idle_pct:.1f}%'
                        
                    text = ax.text(col_idx, row_idx, value_text, ha="center", va="center", 
                                 color='black', fontweight='bold', fontsize=10)
    
    # Create simplified title
    title = f'Connected Idle Time (Active Connected / Total Connected)'
    
    # Titles and labels with larger fonts
    ax.set_title(title, fontsize=18, fontweight='bold', pad=50)
    ax.set_xlabel('Satellite Count', fontsize=16, fontweight='bold')
    ax.set_ylabel('Scheduling Policy & Image Size', fontsize=16, fontweight='bold')
    
    # Add grid for better readability
    ax.set_xticks(np.arange(total_cols+1)-.5, minor=True)
    ax.set_yticks(np.arange(total_rows+1)-.5, minor=True)
    ax.grid(which="minor", color="gray", linestyle='-', linewidth=0.5)
    ax.tick_params(which="minor", size=0)
    
    plt.tight_layout()
    
    # Save the plot to constellation_analysis directory
    script_dir = Path(__file__).parent
    output_dir = script_dir / "constellation_analysis" / "connected_idle_matrix"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "combined_connected_idle_matrix_4d.png"
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"\n✅ 4D Connected Idle Matrix saved: {output_path}")
    
    # Print summary
    print(f"\n=== COMBINED CONNECTED IDLE SUMMARY ===")
    print(f"{'Policy':<12} {'Image Size':<12} {'Satellite Count':<15} {'Strategy':<20} {'Idle Events':<12} {'Idle %':<10}")
    print("-" * 100)
    
    for policy_idx, policy in enumerate(policies):
        for img_idx, img_size in enumerate(image_sizes):
            for strategy_idx, strategy in enumerate(strategies):
                for sat_count_idx, sat_count in enumerate(satellite_counts):
                    row_idx = policy_idx * rows_per_policy + img_idx
                    col_idx = strategy_idx * cols_per_strategy + sat_count_idx
                    
                    idle_count = counts_matrix[row_idx, col_idx]
                    idle_pct = idle_matrix[row_idx, col_idx]
                    
                    if idle_count > 0:  # Only show non-zero entries
                        print(f"{policy.upper():<12} {img_size:>7.3f} MB   {sat_count:<15} {strategy:<20} {int(idle_count):<12} {idle_pct:>6.1f}%")

def main():
    parser = argparse.ArgumentParser(description='Generate combined 4D connected idle time matrix across image sizes and satellite counts using visibility logs')
    parser.add_argument('base_folder', help='Path to folder containing multiple constellation_analysis folders')
    
    args = parser.parse_args()
    
    generate_combined_connected_idle_matrix_4d(args.base_folder)

if __name__ == "__main__":
    main()