#!/usr/bin/env python3
"""Generate combined data efficiency matrix across all image sizes"""

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

def calculate_total_data_accumulated(policy_dir, image_size):
    """Calculate total data accumulated using buffer increase analysis (same as spacing comparison)"""
    total_accumulated = 0
    
    try:
        # Find all buffer files for satellites
        buffer_files = [f for f in os.listdir(policy_dir) if f.startswith('meas-MB-buffered-sat-') and f.endswith('.csv')]
        
        for buffer_file in buffer_files:
            buffer_path = policy_dir / buffer_file
            
            try:
                buffer_df = pd.read_csv(buffer_path)
                if len(buffer_df) > 1 and len(buffer_df.columns) >= 2:
                    # Use the same method as spacing comparison - look at buffer increases
                    buffer_col = buffer_df.columns[1]  # Second column has buffer data
                    buffer_values = pd.to_numeric(buffer_df[buffer_col], errors='coerce').fillna(0)
                    
                    # Calculate buffer increases (data being added to satellite)
                    buffer_increases = buffer_values.diff()
                    # Sum all positive increases (ignore decreases which are downloads)
                    satellite_accumulated = buffer_increases[buffer_increases > 0].sum()
                    
                    total_accumulated += satellite_accumulated
                    
            except Exception as e:
                continue
    
    except Exception as e:
        print(f"   Error calculating accumulated data: {e}")
        return 0
    
    return total_accumulated

def calculate_downloaded_data(policy_dir):
    """Calculate total data downloaded using buffer decrease analysis (same as spacing comparison)"""
    total_downloaded = 0
    
    try:
        # Process ALL buffer files for accurate totals (same method as spacing comparison)
        buffer_files = [f for f in os.listdir(policy_dir) if f.startswith('meas-MB-buffered-sat-') and f.endswith('.csv')]
        
        for buffer_file in buffer_files:
            buffer_path = policy_dir / buffer_file
            if buffer_path.exists():
                try:
                    buffer_df = pd.read_csv(buffer_path)
                    if len(buffer_df) > 1 and len(buffer_df.columns) >= 2:
                        # Use same method as multi_satellite_buffer_bars.py and spacing comparison
                        buffer_col = buffer_df.columns[1]  # Second column has buffer data
                        buffer_df['prev_value'] = buffer_df[buffer_col].shift(1)
                        buffer_df['decrease'] = buffer_df['prev_value'] - buffer_df[buffer_col]
                        
                        # Sum all buffer decreases (data flowing out)
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
    policies = ["sticky", "roundrobin", "fifo", "random"]
    results = {}
    download_data = {}
    accumulated_data = {}  # Add total accumulated data tracking
    
    simulation_logs_zip = strategy_folder / "simulation_logs.zip"
    
    if not simulation_logs_zip.exists():
        print(f"   ❌ No simulation logs found")
        return {policy: 0 for policy in policies}, {policy: 0 for policy in policies}, {policy: 0 for policy in policies}
    
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
                accumulated_data[policy] = total_accumulated  # Store total accumulated
            else:
                results[policy] = 0
                download_data[policy] = 0
                accumulated_data[policy] = 0  # Store zero for missing data
    
    return results, download_data, accumulated_data

def extract_image_size_from_folder(folder_name):
    """Extract image size from folder name like constellation_analysis_20251007_193320_28000_50"""
    # New format: constellation_analysis_YYYYMMDD_HHMMSS_IMAGESIZE_SATCOUNT
    # Try new format first (second-to-last number is image size)
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
    
    # Fallback to old format (last number is image size)
    match = re.search(r'_(\d+)$', folder_name)
    if match:
        size_str = match.group(1)
        # Convert to MB - add decimal point in appropriate position
        if len(size_str) == 5:  # 00028 -> 0.028, 28990 -> 28.990
            return float(size_str) / 1000
        elif len(size_str) == 4:  # Could be 0289 -> 0.289
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
    return None  # If no satellite count found, return None (old format)

def generate_combined_efficiency_matrix(base_folder, satellite_count=None):
    """Generate combined data efficiency matrix for specific satellite count (image size comparison only)"""
    base_path = Path(base_folder)
    
    if not base_path.exists():
        print(f"❌ Base folder not found: {base_folder}")
        return
    
    constellation_info = f" ({satellite_count} satellites)" if satellite_count else ""
    print(f"=== Generating Combined Data Efficiency Matrix{constellation_info} ===")
    print(f"📁 Base folder: {base_folder}")
    
    # Find all analysis folders
    analysis_folders = [f for f in base_path.iterdir() 
                       if f.is_dir() and f.name.startswith('constellation_analysis_')]
    
    if not analysis_folders:
        print(f"❌ No analysis folders found")
        return
    
    # Filter by satellite count if specified
    if satellite_count is not None:
        filtered_folders = []
        for folder in analysis_folders:
            folder_sat_count = extract_satellite_count_from_folder(folder.name)
            if folder_sat_count == satellite_count:
                filtered_folders.append(folder)
        
        if not filtered_folders:
            print(f"❌ No analysis folders found for {satellite_count} satellites")
            print(f"Available satellite counts:")
            sat_counts = set()
            for folder in analysis_folders:
                sat_count = extract_satellite_count_from_folder(folder.name)
                if sat_count is not None:
                    sat_counts.add(sat_count)
            for sc in sorted(sat_counts):
                print(f"  🛰️  {sc} satellites")
            return
        
        analysis_folders = filtered_folders
        print(f"🛰️  Filtering to {satellite_count} satellite constellation ({len(analysis_folders)} folders found)")
    
    # Sort by image size extracted from folder name
    analysis_folders.sort(key=lambda x: extract_image_size_from_folder(x.name) or 0)
    
    print(f"Found {len(analysis_folders)} analysis folders:")
    for folder in analysis_folders:
        img_size = extract_image_size_from_folder(folder.name)
        print(f"  📁 {folder.name} → {img_size:.3f} MB")
    
    strategies = ["close-spaced", "frame-spaced", "orbit-spaced", "close-orbit-spaced"]
    policies = ["sticky", "roundrobin", "fifo", "random"]
    
    # Calculate efficiency for each image size and strategy
    all_efficiency_data = {}
    all_download_data = {}
    all_accumulated_data = {}  # Add accumulated data tracking
    image_sizes = []
    
    for analysis_folder in analysis_folders:
        img_size = extract_image_size_from_folder(analysis_folder.name)
        if img_size is None:
            continue
            
        image_sizes.append(img_size)
        print(f"\n🔄 Processing image size {img_size:.3f} MB...")
        
        efficiency_data = {}
        download_data = {}
        accumulated_data = {}  # Track accumulated data
        
        for strategy in strategies:
            strategy_folder = analysis_folder / strategy
            
            if strategy_folder.exists():
                efficiency_data[strategy], download_data[strategy], accumulated_data[strategy] = calculate_efficiency_for_strategy(strategy_folder)
                print(f"   ✅ {strategy}: Processed")
            else:
                print(f"   ❌ {strategy}: Not found")
                efficiency_data[strategy] = {policy: 0 for policy in policies}
                download_data[strategy] = {policy: 0 for policy in policies}
                accumulated_data[strategy] = {policy: 0 for policy in policies}  # Initialize accumulated data
        
        all_efficiency_data[img_size] = efficiency_data
        all_download_data[img_size] = download_data
        all_accumulated_data[img_size] = accumulated_data  # Store accumulated data
    
    if not image_sizes:
        print("❌ No valid analysis folders found")
        return
    
    # Create combined matrix (policies × strategies, with each cell showing all 4 image sizes)
    # We'll use a larger matrix where each "cell" is actually 4 sub-cells vertically stacked
    rows_per_policy = len(image_sizes)  # 4 image sizes per policy
    total_rows = len(policies) * rows_per_policy
    
    efficiency_matrix = np.zeros((total_rows, len(strategies)))
    download_matrix = np.zeros((total_rows, len(strategies)))
    accumulated_matrix = np.zeros((total_rows, len(strategies)))  # Add accumulated data matrix
    
    # Fill the matrix: each policy gets 4 rows (one per image size)
    for policy_idx, policy in enumerate(policies):
        for img_idx, img_size in enumerate(image_sizes):
            row_idx = policy_idx * rows_per_policy + img_idx
            
            for strategy_idx, strategy in enumerate(strategies):
                efficiency = all_efficiency_data[img_size][strategy][policy]
                download = all_download_data[img_size][strategy][policy]
                accumulated = all_accumulated_data[img_size][strategy][policy]  # Get accumulated data
                
                efficiency_matrix[row_idx, strategy_idx] = efficiency
                download_matrix[row_idx, strategy_idx] = download
                accumulated_matrix[row_idx, strategy_idx] = accumulated  # Store accumulated data
    
    # Create the plot with adjusted size for the larger matrix
    fig, ax = plt.subplots(figsize=(16, 14))
    
    # Use Reds colormap for inefficiency (higher inefficiency = worse = darker red)
    # Create inefficiency matrix for consistent coloring with other scripts
    inefficiency_matrix = 100 - efficiency_matrix
    cmap = 'Reds'
    better_text = "Lower Values = Better Performance (Less Waste)"
    
    # Create the heatmap using imshow with inefficiency for coloring
    im = ax.imshow(inefficiency_matrix, cmap=cmap, aspect='auto', vmin=0, vmax=100)
    
    # Set ticks and labels - strategies on X, policies with image sizes on Y
    strategy_labels = [s.replace('-', '-').title() for s in strategies]
    
    # Create Y-axis labels: Show both policy names and image sizes
    all_y_positions = []
    all_y_labels = []
    
    for policy_idx, policy in enumerate(policies):
        for img_idx, img_size in enumerate(image_sizes):
            row_idx = policy_idx * rows_per_policy + img_idx
            all_y_positions.append(row_idx)
            
            # Format image size for clean display (e.g., 0.028 -> .028, 28.990 -> 29)
            if img_size < 1:
                size_label = f".{int(img_size * 1000):03d}"  # .028, .289
            else:
                size_label = f"{img_size:.0f}"  # 3, 29
            
            # For the first row of each policy, show policy name to the left of image size
            if img_idx == 0:
                label = f"{policy.upper()}  {size_label}"  # Extra space for separation
            else:
                label = f"      {size_label}"  # Indent image sizes to align under policy
            
            all_y_labels.append(label)
    
    ax.set_xticks(np.arange(len(strategies)))
    ax.set_yticks(all_y_positions)
    ax.set_xticklabels(strategy_labels, fontsize=12, fontweight='bold')
    ax.set_yticklabels(all_y_labels, fontsize=10, fontweight='bold')
    
    # Add colorbar
    max_value = np.max(efficiency_matrix)
    min_value = np.min(efficiency_matrix)
    cbar = plt.colorbar(im, ax=ax, shrink=0.8)
    cbar.set_label('Download Inefficiency (%)', rotation=270, labelpad=20, fontsize=12, fontweight='bold')
    cbar.ax.tick_params(labelsize=10)
    
    # Add text annotations with values - show downloaded/accumulated format
    for policy_idx, policy in enumerate(policies):
        for img_idx, img_size in enumerate(image_sizes):
            row_idx = policy_idx * rows_per_policy + img_idx
            
            for strategy_idx, strategy in enumerate(strategies):
                downloaded_mb = download_matrix[row_idx, strategy_idx]
                accumulated_mb = accumulated_matrix[row_idx, strategy_idx]
                efficiency_pct = efficiency_matrix[row_idx, strategy_idx]
                
                # Calculate inefficiency percentage for consistent coloring
                inefficiency_pct = 100 - efficiency_pct
                
                # Format text showing downloaded/accumulated and inefficiency percentage
                if accumulated_mb >= 1000:  # Use GB for large values
                    downloaded_gb = downloaded_mb / 1000
                    accumulated_gb = accumulated_mb / 1000
                    value_text = f'{downloaded_gb:.1f}/{accumulated_gb:.1f} GB\n{inefficiency_pct:.1f}%'
                else:
                    value_text = f'{downloaded_mb:.0f}/{accumulated_mb:.0f} MB\n{inefficiency_pct:.1f}%'
                    
                text = ax.text(strategy_idx, row_idx, value_text, ha="center", va="center", 
                             color='black', fontweight='bold', fontsize=9)
    
    # Create comprehensive title
    constellation_title = f" ({satellite_count} Satellite Constellation)" if satellite_count else ""
    title = f'Data Download Efficiency{constellation_title} (Downloaded / Total Accumulated)\nEach cell shows 4 image sizes: {", ".join([f"{s:.3f}MB" for s in image_sizes])}\n{better_text}'
    
    # Titles and labels
    ax.set_title(title, fontsize=16, fontweight='bold', pad=25)
    ax.set_xlabel('Spacing Strategy', fontsize=14, fontweight='bold')
    ax.set_ylabel('Scheduling Policy (with Image Sizes)', fontsize=14, fontweight='bold')
    
    # Add horizontal grid lines to separate policies (every 4 rows)
    for policy_idx in range(1, len(policies)):
        ax.axhline(y=policy_idx * rows_per_policy - 0.5, color='black', linestyle='-', linewidth=3)
    
    # Add grid for better readability
    ax.set_xticks(np.arange(len(strategies)+1)-.5, minor=True)
    ax.set_yticks(np.arange(total_rows+1)-.5, minor=True)
    ax.grid(which="minor", color="gray", linestyle='-', linewidth=1)
    ax.tick_params(which="minor", size=0)
    
    # Rotate labels for better readability
    plt.xticks(rotation=45, ha='right')
    plt.yticks(rotation=0)
    
    plt.tight_layout()
    
    # Save the plot with satellite count in filename to constellation_analysis/efficiency_matrix/
    if satellite_count is not None:
        output_filename = f'combined_efficiency_matrix_{satellite_count}sats.png'
    else:
        output_filename = 'combined_efficiency_matrix.png'
    
    # Save to constellation_analysis/efficiency_matrix/ directory
    script_dir = Path(__file__).parent
    output_dir = script_dir / "constellation_analysis" / "efficiency_matrix"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / output_filename
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"\n✅ Combined efficiency matrix saved: {output_path}")
    
    # Print summary showing best performance for each policy across all image sizes
    print(f"\n=== COMBINED EFFICIENCY SUMMARY ===")
    print(f"{'Policy':<15} {'Image Size':<12} {'Best Strategy':<20} {'Download':<12} {'Efficiency':<12}")
    print("-" * 85)
    
    for policy_idx, policy in enumerate(policies):
        for img_idx, img_size in enumerate(image_sizes):
            row_idx = policy_idx * rows_per_policy + img_idx
            row_efficiencies = efficiency_matrix[row_idx, :]
            best_strategy_idx = np.argmax(row_efficiencies)
            best_strategy = strategies[best_strategy_idx]
            best_efficiency = row_efficiencies[best_strategy_idx]
            best_download = download_matrix[row_idx, best_strategy_idx] / 1000  # Convert to GB
            
            print(f"{policy.upper():<15} {img_size:>7.3f} MB   {best_strategy:<20} {best_download:>8.1f} GB   {best_efficiency:>8.1f}%")

def main():
    parser = argparse.ArgumentParser(description='Generate combined data efficiency matrix across image sizes for specific satellite count')
    parser.add_argument('base_folder', help='Path to folder containing multiple analysis folders')
    parser.add_argument('--sats', type=int, help='Satellite count to filter by (e.g., 1, 50, 100, 200)')
    args = parser.parse_args()
    
    generate_combined_efficiency_matrix(args.base_folder, args.sats)

if __name__ == "__main__":
    main()