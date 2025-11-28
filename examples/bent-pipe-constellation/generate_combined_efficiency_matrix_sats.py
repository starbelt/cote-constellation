#!/usr/bin/env python3
"""Generate combined data efficiency matrix across all image sizes

CALCULATION METHOD (Updated to use visibility_log.csv):
- NUMERATOR (Total Downloaded): Sum downloaded_mb where connected == 1
  * downloaded_mb column contains actual drainBuffer() return values
  * This fixes undercount bug from buffer decrease method (missed simultaneous events)
  
- DENOMINATOR (Total Buffered/Accumulated): Count image_taken flags × image_size_mb
  * image_size_mb = bits_per_sense (from sensor.dat) ÷ 8 ÷ 1e6 (decimal MB)
  * This fixes undercount bug from buffer increase method
  
- Efficiency = (Total Downloaded / Total Accumulated) × 100%
  * How much of the buffered data was successfully downlinked

See NUMERATOR_DENOMINATOR_FIX.md and COUNTING_BUG_EXPLANATION.md for details.
"""

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
    """Read configuration from simulation_logs.zip to get bits-per-sense"""
    config = {}
    try:
        with zipfile.ZipFile(zip_path, 'r') as zipf:
            # Read sensor configuration
            if 'configuration/sensor.dat' in zipf.namelist():
                with zipf.open('configuration/sensor.dat') as f:
                    content = f.read().decode().strip()
                    lines = content.split('\n')
                    
                    # Try the comma-separated format first
                    if len(lines) >= 2 and ',' in lines[1]:
                        # Format: bits-per-sense,pixel-count,pixel-size-m,focal-length-m,max-buffer-mb
                        data = lines[1].split(',')
                        if len(data) >= 1:
                            # Get bits-per-sense and convert to DECIMAL MB (÷ 1,000,000)
                            bits_per_sense = int(data[0])
                            image_size_mb = (bits_per_sense / 8.0) / 1e6  # Decimal MB, not binary MiB
                            config['image_size'] = image_size_mb
                    else:
                        # Try the space-separated format
                        for line in lines:
                            if line.startswith('sensor-image-size-MB'):
                                config['image_size'] = float(line.split()[-1])
    except Exception as e:
        print(f"Warning: Could not read config from zip: {e}")
        config['image_size'] = 29.360128  # Default fallback (234881024 bits in decimal MB)
    
    return config

def calculate_total_data_accumulated(policy_dir, image_size):
    """Calculate total data accumulated using image_taken flags from visibility_log.csv"""
    total_accumulated = 0
    
    try:
        # Read visibility_log.csv
        visibility_log_path = policy_dir / 'visibility_log.csv'
        
        if visibility_log_path.exists():
            # Read the visibility log
            df = pd.read_csv(visibility_log_path)
            
            # Count total images taken (image_taken == 1)
            total_images = len(df[df['image_taken'] == 1])
            
            # Calculate total accumulated data
            total_accumulated = total_images * image_size
            
        else:
            print(f"      ⚠️  visibility_log.csv not found, using fallback method")
            # Fallback to old method if visibility_log doesn't exist
            buffer_files = [f for f in os.listdir(policy_dir) if f.startswith('meas-MB-buffered-sat-') and f.endswith('.csv')]
            
            for buffer_file in buffer_files:
                buffer_path = policy_dir / buffer_file
                
                try:
                    buffer_df = pd.read_csv(buffer_path)
                    if len(buffer_df) > 1 and len(buffer_df.columns) >= 2:
                        buffer_col = buffer_df.columns[1]
                        buffer_values = pd.to_numeric(buffer_df[buffer_col], errors='coerce').fillna(0)
                        buffer_increases = buffer_values.diff()
                        satellite_accumulated = buffer_increases[buffer_increases > 0].sum()
                        total_accumulated += satellite_accumulated
                        
                except Exception as e:
                    continue
                    
    except Exception as e:
        print(f"   Error calculating accumulated data: {e}")
        return 0
    
    return total_accumulated

def calculate_downloaded_data(policy_dir):
    """Calculate total data downloaded using downloaded_mb column from visibility_log.csv"""
    total_downloaded = 0
    
    try:
        # Read visibility_log.csv
        visibility_log_path = policy_dir / 'visibility_log.csv'
        
        if visibility_log_path.exists():
            # Read the visibility log
            df = pd.read_csv(visibility_log_path)
            
            # Sum downloaded_mb where connected == 1
            total_downloaded = df[df['connected'] == 1]['downloaded_mb'].sum()
            
        else:
            print(f"      ⚠️  visibility_log.csv not found, using fallback method")
            # Fallback to old method if visibility_log doesn't exist
            buffer_files = [f for f in os.listdir(policy_dir) if f.startswith('meas-MB-buffered-sat-') and f.endswith('.csv')]
            
            for buffer_file in buffer_files:
                buffer_path = policy_dir / buffer_file
                if buffer_path.exists():
                    try:
                        buffer_df = pd.read_csv(buffer_path)
                        if len(buffer_df) > 1 and len(buffer_df.columns) >= 2:
                            buffer_col = buffer_df.columns[1]
                            buffer_df['prev_value'] = buffer_df[buffer_col].shift(1)
                            buffer_df['decrease'] = buffer_df['prev_value'] - buffer_df[buffer_col]
                            satellite_downloaded = buffer_df[buffer_df['decrease'] > 0]['decrease'].sum()
                            total_downloaded += satellite_downloaded
                    except Exception:
                        continue
                        
    except Exception as e:
        print(f"   Error calculating downloaded data: {e}")
        return 0
    
    return total_downloaded

def calculate_efficiency_for_strategy(strategy_folder):
    """Calculate efficiency percentages and absolute downloads for all policies in a strategy"""
    policies = ["sticky", "roundrobin", "fifo", "random", "mindistance", "maxdownload"]
    results = {}
    download_data = {}
    
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
                # Calculate total data that would have accumulated using buffer increase analysis
                total_accumulated = calculate_total_data_accumulated(policy_dir, image_size)
                
                # Calculate total data downloaded using buffer decrease analysis (same as spacing comparison)
                total_downloaded = calculate_downloaded_data(policy_dir)
                
                # Calculate efficiency percentage
                if total_accumulated > 0:
                    efficiency = (total_downloaded / total_accumulated) * 100
                else:
                    efficiency = 0
                
                results[policy] = efficiency
                download_data[policy] = total_downloaded
            else:
                results[policy] = 0
                download_data[policy] = 0
    
    return results, download_data

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
    return None

def extract_params_from_folder(folder_name):
    """Extract both image size and satellite count from folder name"""
    image_size = extract_image_size_from_folder(folder_name)
    sat_count = extract_satellite_count_from_folder(folder_name)
    return image_size, sat_count

def generate_combined_efficiency_matrix(base_folder, metric='percentage'):
    """Generate combined data efficiency matrix for all image sizes, satellite counts and strategies
    
    Args:
        base_folder: Path to folder containing analysis folders
        metric: 'percentage' for efficiency % or 'absdata' for absolute GB downloaded
    """
    base_path = Path(base_folder)
    
    if not base_path.exists():
        print(f"❌ Base folder not found: {base_folder}")
        return
    
    print(f"=== Generating Combined 4D Data Efficiency Matrix ===")
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
    print(f"  � Image sizes: {[f'{size:.3f} MB' for size in image_sizes]}")
    print(f"  🛰️  Satellite counts: {satellite_counts}")
    print(f"  📊 Total combinations: {len(image_sizes)} × {len(satellite_counts)} = {len(image_sizes) * len(satellite_counts)}")
    
    strategies = ["close-spaced", "frame-spaced", "orbit-spaced", "close-orbit-spaced"]
    policies = ["sticky", "roundrobin", "fifo", "random", "mindistance", "maxdownload"]
    
    # Calculate efficiency for each parameter combination
    all_efficiency_data = {}
    all_download_data = {}
    
    for img_size in image_sizes:
        all_efficiency_data[img_size] = {}
        all_download_data[img_size] = {}
        
        for sat_count in satellite_counts:
            if sat_count in param_groups[img_size]:
                analysis_folder = param_groups[img_size][sat_count]
                print(f"\n🔄 Processing {img_size:.3f} MB, {sat_count} sats...")
                
                efficiency_data = {}
                download_data = {}
                
                for strategy in strategies:
                    strategy_folder = analysis_folder / strategy
                    
                    if strategy_folder.exists():
                        efficiency_data[strategy], download_data[strategy] = calculate_efficiency_for_strategy(strategy_folder)
                        print(f"   ✅ {strategy}: Processed")
                    else:
                        print(f"   ❌ {strategy}: Not found")
                        efficiency_data[strategy] = {policy: 0 for policy in policies}
                        download_data[strategy] = {policy: 0 for policy in policies}
                
                all_efficiency_data[img_size][sat_count] = efficiency_data
                all_download_data[img_size][sat_count] = download_data
            else:
                print(f"\n⚠️  Missing data for {img_size:.3f} MB, {sat_count} sats")
                # Fill with zeros for missing combinations
                all_efficiency_data[img_size][sat_count] = {
                    strategy: {policy: 0 for policy in policies} 
                    for strategy in strategies
                }
                all_download_data[img_size][sat_count] = {
                    strategy: {policy: 0 for policy in policies} 
                    for strategy in strategies
                }
    
    if not image_sizes or not satellite_counts:
        print("❌ No valid analysis folders found")
        return
    
    # Create 4D matrix: each "big cell" (policy×strategy) is subdivided into:
    # - 4 rows (image sizes) × 4 columns (satellite counts) = 16 sub-cells
    rows_per_policy = len(image_sizes)  # 4 image sizes per policy
    cols_per_strategy = len(satellite_counts)  # 4 satellite counts per strategy
    total_rows = len(policies) * rows_per_policy
    total_cols = len(strategies) * cols_per_strategy
    
    efficiency_matrix = np.zeros((total_rows, total_cols))
    download_matrix = np.zeros((total_rows, total_cols))
    
    # Fill the matrix: each policy×strategy combination gets a 4×4 sub-matrix
    for policy_idx, policy in enumerate(policies):
        for img_idx, img_size in enumerate(image_sizes):
            row_idx = policy_idx * rows_per_policy + img_idx
            
            for strategy_idx, strategy in enumerate(strategies):
                for sat_idx, sat_count in enumerate(satellite_counts):
                    col_idx = strategy_idx * cols_per_strategy + sat_idx
                    
                    efficiency = all_efficiency_data[img_size][sat_count][strategy][policy]
                    download = all_download_data[img_size][sat_count][strategy][policy]
                    
                    efficiency_matrix[row_idx, col_idx] = efficiency
                    download_matrix[row_idx, col_idx] = download
    
    # Create the plot with adjusted size for the much larger 4D matrix
    fig, ax = plt.subplots(figsize=(24, 18))  # Larger to accommodate 4x more columns
    
    # Configure visualization based on metric
    if metric == 'absdata':
        # Use Greens colormap for total data downloaded (higher data = better = darker green)
        cmap = 'Greens'
        better_text = "Higher Values = Better Performance (More Data Downloaded)"
        data_matrix = download_matrix / 1000  # Convert MB to GB for display
        colorbar_label = 'Total Data Downloaded (GB)'
    else:  # percentage
        # Use Greens colormap for efficiency percentage
        cmap = 'Greens'
        better_text = "Higher Values = Better Efficiency (%)"
        data_matrix = efficiency_matrix
        colorbar_label = 'Data Download Efficiency (%)'
    
    # Create the heatmap
    im = ax.imshow(data_matrix, cmap=cmap, aspect='auto')
    
    # Create strategy labels that repeat for each satellite count
    strategy_labels = []
    for strategy in strategies:
        strategy_name = strategy.replace('-', '-').title()
        for sat_count in satellite_counts:
            strategy_labels.append(f"{strategy_name}\n{sat_count} Sats")
    
    # Create Y-axis labels: Show both policy names and image sizes  
    all_y_positions = []
    all_y_labels = []
    
    for policy_idx, policy in enumerate(policies):
        for img_idx, img_size in enumerate(image_sizes):
            row_idx = policy_idx * rows_per_policy + img_idx
            all_y_positions.append(row_idx)
            
            # Format image size for clean display
            if img_size < 1:
                size_label = f".{int(img_size * 1000):03d}"  # .028, .289
            else:
                size_label = f"{img_size:.0f}"  # 3, 29
            
            # For the first row of each policy, show policy name
            if img_idx == 0:
                label = f"{policy.upper()}  {size_label}"
            else:
                label = f"      {size_label}"
            
            all_y_labels.append(label)
    
    ax.set_xticks(np.arange(total_cols))
    ax.set_yticks(all_y_positions)
    ax.set_xticklabels(strategy_labels, fontsize=9, fontweight='bold', rotation=45, ha='right')
    ax.set_yticklabels(all_y_labels, fontsize=10, fontweight='bold')
    
    # Add separator lines to visually distinguish the big cells
    # Vertical lines between strategies
    for strategy_idx in range(1, len(strategies)):
        x_pos = strategy_idx * cols_per_strategy - 0.5
        ax.axvline(x=x_pos, color='black', linewidth=2)
    
    # Horizontal lines between policies  
    for policy_idx in range(1, len(policies)):
        y_pos = policy_idx * rows_per_policy - 0.5
        ax.axhline(y=y_pos, color='black', linewidth=2)
    
    # Add colorbar
    cbar = plt.colorbar(im, ax=ax, shrink=0.6)
    cbar.set_label(colorbar_label, rotation=270, labelpad=20, fontsize=12, fontweight='bold')
    cbar.ax.tick_params(labelsize=10)
    
    # Add text annotations with values 
    for policy_idx, policy in enumerate(policies):
        for img_idx, img_size in enumerate(image_sizes):
            row_idx = policy_idx * rows_per_policy + img_idx
            
            for strategy_idx, strategy in enumerate(strategies):
                for sat_idx, sat_count in enumerate(satellite_counts):
                    col_idx = strategy_idx * cols_per_strategy + sat_idx
                    
                    download_gb = download_matrix[row_idx, col_idx] / 1000  # Convert MB to GB
                    efficiency_pct = efficiency_matrix[row_idx, col_idx]
                    
                    # Format text based on metric choice
                    if metric == 'absdata':
                        # Show download data prominently, efficiency as secondary
                        if download_gb >= 1000:  # Use TB for very large values
                            value_text = f'{download_gb/1000:.1f}TB\n{efficiency_pct:.1f}%'
                        elif download_gb >= 1:
                            value_text = f'{download_gb:.1f}GB\n{efficiency_pct:.1f}%'
                        else:
                            value_text = f'{download_matrix[row_idx, col_idx]:.0f}MB\n{efficiency_pct:.1f}%'
                    else:  # percentage
                        # Show efficiency prominently, download as secondary
                        if download_gb >= 1000:  # Use TB for very large values
                            value_text = f'{efficiency_pct:.1f}%\n{download_gb/1000:.1f}TB'
                        elif download_gb >= 1:
                            value_text = f'{efficiency_pct:.1f}%\n{download_gb:.1f}GB'
                        else:
                            value_text = f'{efficiency_pct:.1f}%\n{download_matrix[row_idx, col_idx]:.0f}MB'
                        
                    ax.text(col_idx, row_idx, value_text, ha="center", va="center", 
                           color='black', fontweight='bold', fontsize=7)  # Smaller font for 4D matrix
    
    # Create comprehensive title
    img_size_str = ", ".join([f"{s:.3f}MB" for s in image_sizes])
    sat_count_str = ", ".join([f"{sc}" for sc in satellite_counts])
    
    if metric == 'absdata':
        title = f'4D Data Download Volume Matrix (Shaded by Total GB Downloaded)\nImage Sizes: {img_size_str} | Satellite Counts: {sat_count_str}\nEach cell shows: Total Downloaded | Efficiency % | {better_text}'
    else:  # percentage
        title = f'4D Data Download Efficiency Matrix (Shaded by Efficiency %)\nImage Sizes: {img_size_str} | Satellite Counts: {sat_count_str}\nEach cell shows: Efficiency % | Total Downloaded | {better_text}'
    
    # Titles and labels
    ax.set_title(title, fontsize=16, fontweight='bold', pad=25)
    ax.set_xlabel('Spacing Strategy × Satellite Count', fontsize=14, fontweight='bold')
    ax.set_ylabel('Scheduling Policy × Image Size', fontsize=14, fontweight='bold')
    
    # Add grid lines to separate the big cells
    # Already added separator lines above, just add minor grid
    ax.set_xticks(np.arange(total_cols+1)-.5, minor=True)
    ax.set_yticks(np.arange(total_rows+1)-.5, minor=True)
    ax.grid(which="minor", color="lightgray", linestyle='-', linewidth=0.5, alpha=0.3)
    ax.tick_params(which="minor", size=0)
    
    plt.tight_layout()
    
    # Save the plot with metric-specific filename to constellation_analysis/efficiency_matrix/
    if metric == 'absdata':
        output_filename = 'combined_4d_efficiency_matrix_absdata.png'
    else:
        output_filename = 'combined_4d_efficiency_matrix_percentage.png'
    
    # Save to constellation_analysis/efficiency_matrix/ directory
    script_dir = Path(__file__).parent
    output_dir = script_dir / "constellation_analysis" / "efficiency_matrix"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / output_filename
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"\n✅ Combined 4D efficiency matrix saved: {output_path}")
    
    # Save the raw data with proper 4D structure
    # Create DataFrame with multi-index for the 4D data
    row_index = []
    for policy in policies:
        for img_size in image_sizes:
            row_index.append(f"{policy.upper()}_{img_size:.3f}MB")
    
    col_index = []  
    for strategy in strategies:
        for sat_count in satellite_counts:
            col_index.append(f"{strategy}_{sat_count}sats")
    
    # Print summary showing best performance for each policy×image×satellite combination
    print(f"\n=== COMBINED 4D EFFICIENCY SUMMARY ===")
    print(f"{'Policy':<12} {'Image Size':<10} {'Sat Count':<10} {'Best Strategy':<20} {'Download':<12} {'Efficiency':<12}")
    print("-" * 85)
    
    for policy in policies:
        for img_size in image_sizes:
            for sat_count in satellite_counts:
                # Find best strategy for this specific combination
                best_efficiency = 0
                best_strategy = ""
                best_download = 0
                
                for strategy in strategies:
                    efficiency = all_efficiency_data[img_size][sat_count][strategy][policy]
                    download = all_download_data[img_size][sat_count][strategy][policy]
                    
                    if efficiency > best_efficiency:
                        best_efficiency = efficiency
                        best_strategy = strategy
                        best_download = download / 1000  # Convert to GB
                
                print(f"{policy.upper():<12} {img_size:>7.3f} MB {sat_count:>7} {best_strategy:<20} {best_download:>8.1f} GB   {best_efficiency:>8.1f}%")

def main():
    parser = argparse.ArgumentParser(description='Generate combined 4D data efficiency matrix across image sizes and satellite counts')
    parser.add_argument('base_folder', help='Path to folder containing multiple analysis folders')
    parser.add_argument('--metric', choices=['percentage', 'absdata'], default='percentage',
                       help='Metric to visualize: percentage (efficiency %%) or absdata (absolute GB downloaded)')
    args = parser.parse_args()
    
    generate_combined_efficiency_matrix(args.base_folder, metric=args.metric)

if __name__ == "__main__":
    main()