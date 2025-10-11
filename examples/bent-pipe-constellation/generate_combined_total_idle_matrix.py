#!/usr/bin/env python3
"""Generate combined total idle time matrix (overall system utilization) using visibility logs across all image sizes"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import seaborn as sns
import zipfile
import tempfile
import argparse
from pathlib import Path
import re

def read_config_from_zip(zip_path):
    """Read configuration from zip file"""
    config = {}
    try:
        with zipfile.ZipFile(zip_path, 'r') as zipf:
            # Look for configuration file
            config_files = [f for f in zipf.namelist() if 'configuration' in f and f.endswith('.dat')]
            if config_files:
                with zipf.open(config_files[0]) as f:
                    content = f.read().decode('utf-8')
                    lines = content.strip().split('\n')
                    if len(lines) >= 2:
                        # Parse image size from second line - look for a float value
                        parts = lines[1].split()
                        for part in parts:
                            try:
                                # Try to find a float that could be image size
                                val = float(part.replace(',', '.'))
                                if 0.001 <= val <= 100:  # Reasonable image size range
                                    config['image_size'] = val
                                    break
                            except ValueError:
                                continue
    except Exception as e:
        # Silently fall back to folder name extraction
        pass
    
    return config

def calculate_total_idle_from_visibility_log(strategy_folder):
    """Calculate total idle time from visibility_log.csv"""
    policies = ["sticky", "roundrobin", "fifo", "random"]
    results = {}
    idle_data = {}
    
    simulation_logs_zip = strategy_folder / "simulation_logs.zip"
    
    if not simulation_logs_zip.exists():
        print(f"   ❌ No simulation logs found")
        return {policy: 0 for policy in policies}, {policy: 0 for policy in policies}
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        with zipfile.ZipFile(simulation_logs_zip, 'r') as zipf:
            zipf.extractall(temp_path)
        
        for policy in policies:
            policy_dir = temp_path / policy
            visibility_log_path = policy_dir / "visibility_log.csv"
            
            if policy_dir.exists() and visibility_log_path.exists():
                try:
                    # Read visibility log
                    df = pd.read_csv(visibility_log_path)
                    
                    if len(df) == 0:
                        results[policy] = 0
                        idle_data[policy] = 0
                        continue
                    
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
                    
                    # Calculate percentage
                    total_idle_percentage = (total_idle_time / sim_duration) * 100
                    total_idle_percentage = max(0, min(100, total_idle_percentage))
                    
                    results[policy] = total_idle_percentage
                    idle_data[policy] = total_idle_time
                    
                    print(f"   {policy}: {actual_productive_time}/{sim_duration}s productive time = {total_idle_percentage:.1f}% total idle")
                    
                except Exception as e:
                    print(f"   Error processing {policy}: {e}")
                    results[policy] = 0
                    idle_data[policy] = 0
            else:
                print(f"   ⚠️  {policy}: No visibility log found")
                results[policy] = 0
                idle_data[policy] = 0
    
    return results, idle_data

def extract_image_size_from_folder(folder_name):
    """Extract image size from folder name like constellation_analysis_20251009_152226_00027_50"""
    match = re.search(r'_(\d+)_\d+$', folder_name)
    if match:
        size_str = match.group(1)
        # Convert to MB - add decimal point in appropriate position
        if len(size_str) == 5:  # 00027 -> 0.027
            return float(size_str) / 1000
        elif len(size_str) == 4:  # 0279 -> 0.279  
            return float(size_str) / 1000
        else:
            return float(size_str) / 1000
    return None

def extract_satellite_count_from_folder(folder_name):
    """Extract satellite count from folder name"""
    match = re.search(r'_(\d+)$', folder_name)
    if match:
        return int(match.group(1))
    return None

def generate_combined_total_idle_matrix_visibility(base_folder, satellite_count=None):
    """Generate total idle time matrix for specific satellite count"""
    base_path = Path(base_folder)
    
    if not base_path.exists():
        print(f"❌ Base folder not found: {base_folder}")
        return
    
    constellation_info = f" ({satellite_count} satellites)" if satellite_count else ""
    print(f"=== Generating Total Idle Time Matrix{constellation_info} ===")
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
            available_counts = set()
            for folder in analysis_folders:
                count = extract_satellite_count_from_folder(folder.name)
                if count is not None:
                    available_counts.add(count)
            print("Available satellite counts:")
            for count in sorted(available_counts):
                print(f"  🛰️  {count} satellites")
            return
        
        analysis_folders = filtered_folders
        print(f"🛰️  Filtering to {satellite_count} satellite constellation ({len(analysis_folders)} folders found)")
    
    # Group folders by image size
    size_to_folders = {}
    for folder in analysis_folders:
        image_size = extract_image_size_from_folder(folder.name)
        if image_size is not None:
            if image_size not in size_to_folders:
                size_to_folders[image_size] = []
            size_to_folders[image_size].append(folder)
    
    if not size_to_folders:
        print(f"❌ No valid analysis folders found")
        return
    
    # Sort image sizes
    sorted_sizes = sorted(size_to_folders.keys())
    
    print("Found analysis folders:")
    for size in sorted_sizes:
        folders = size_to_folders[size]
        print(f"  📁 {folders[0].name} → {size:.3f} MB")
    
    # Strategies and policies
    strategies = ["close-spaced", "frame-spaced", "orbit-spaced", "close-orbit-spaced"]
    policies = ["sticky", "roundrobin", "fifo", "random"]
    
    # Initialize data structure
    data = {}
    all_idle_counts = {}
    
    for size in sorted_sizes:
        folder = size_to_folders[size][0]  # Use first (should be only) folder for this size
        print(f"\n🔄 Processing image size {size:.3f} MB...")
        
        data[size] = {}
        all_idle_counts[size] = {}
        
        for strategy in strategies:
            strategy_folder = folder / strategy
            
            if strategy_folder.exists():
                idle_percentages, idle_counts = calculate_total_idle_from_visibility_log(strategy_folder)
                data[size][strategy] = idle_percentages
                all_idle_counts[size][strategy] = idle_counts
                print(f"   ✅ {strategy}: Processed")
            else:
                print(f"   ❌ {strategy}: Not found")
                data[size][strategy] = {policy: 0 for policy in policies}
                all_idle_counts[size][strategy] = {policy: 0 for policy in policies}
    
    # Create single comprehensive matrix
    rows_per_policy = len(sorted_sizes)
    total_rows = len(policies) * rows_per_policy
    
    # Create matrices for visualization
    total_idle_matrix = np.zeros((total_rows, len(strategies)))
    total_idle_counts_matrix = np.zeros((total_rows, len(strategies)))
    
    # Fill matrices
    for policy_idx, policy in enumerate(policies):
        for size_idx, size in enumerate(sorted_sizes):
            row_idx = policy_idx * rows_per_policy + size_idx
            
            for strategy_idx, strategy in enumerate(strategies):
                total_idle_matrix[row_idx, strategy_idx] = data[size][strategy][policy]
                total_idle_counts_matrix[row_idx, strategy_idx] = all_idle_counts[size][strategy][policy]
    
    # Create comprehensive visualization
    plt.figure(figsize=(16, 12))
    ax = plt.gca()
    
    # Import color utilities for custom colormap
    from matplotlib.colors import BoundaryNorm
    import matplotlib.colors as mcolors
    
    # Create custom colormap for total idle (orange gradient as this represents system utilization)
    # Define boundaries for color mapping (0-100% range)
    boundaries = np.linspace(0, 100, 11)  # 0, 10, 20, ..., 100
    colors = [
        '#ffffff',  # White (0% - best performance, unlikely for total idle)
        '#fff5e6',  # Very light orange (0-10%)
        '#ffebcc',  # Light orange (10-20%)
        '#ffe0b3',  # Light-medium orange (20-30%)
        '#ffd699',  # Medium orange (30-40%)
        '#ffcc80',  # Medium-dark orange (40-50%)
        '#ffc266',  # Dark orange (50-60%)
        '#ffb84d',  # Darker orange (60-70%)
        '#ffad33',  # Very dark orange (70-80%)
        '#ffa31a',  # Almost darkest orange (80-90%)
        '#ff9900'   # Bright orange (90-100% - expected for total idle)
    ]
    cmap = mcolors.ListedColormap(colors)
    norm = BoundaryNorm(boundaries, cmap.N)
    
    # Create heatmap with custom colormap
    im = ax.imshow(total_idle_matrix, cmap=cmap, aspect='auto', norm=norm)
    
    # Create labels
    strategy_labels = [s.replace('-', ' ').title() for s in strategies]
    
    # Y-axis labels: Policy + Image Size
    all_y_labels = []
    all_y_positions = []
    
    for policy_idx, policy in enumerate(policies):
        for size_idx, size in enumerate(sorted_sizes):
            row_idx = policy_idx * rows_per_policy + size_idx
            
            if size_idx == 0:
                # First image size for this policy - show policy name
                label = f"{policy.upper()}\n{size:.3f}MB"
            else:
                # Subsequent image sizes - show just the size
                label = f"{size:.3f}MB"
            
            all_y_labels.append(label)
            all_y_positions.append(row_idx)
    
    # Set axis labels and ticks
    ax.set_xticks(range(len(strategies)))
    ax.set_yticks(all_y_positions)
    ax.set_xticklabels(strategy_labels, fontsize=12, fontweight='bold')
    ax.set_yticklabels(all_y_labels, fontsize=10, fontweight='bold')
    
    # Add colorbar
    max_value = np.max(total_idle_matrix)
    min_value = np.min(total_idle_matrix)
    cbar = plt.colorbar(im, ax=ax, shrink=0.8)
    cbar.set_label('Total Idle Time (%)', rotation=270, labelpad=20, fontsize=12, fontweight='bold')
    cbar.ax.tick_params(labelsize=10)
    
    # Add text annotations with values - show time format and percentage
    for policy_idx, policy in enumerate(policies):
        for img_idx, img_size in enumerate(sorted_sizes):
            row_idx = policy_idx * rows_per_policy + img_idx
            
            for strategy_idx, strategy in enumerate(strategies):
                total_idle_time = total_idle_counts_matrix[row_idx, strategy_idx]
                total_idle_pct = total_idle_matrix[row_idx, strategy_idx]
                
                # Format text showing time in seconds and percentage
                value_text = f'{int(total_idle_time)}s\n{total_idle_pct:.1f}%'
                    
                text = ax.text(strategy_idx, row_idx, value_text, ha="center", va="center", 
                             color='black', fontweight='bold', fontsize=9)
    
    # Create comprehensive title
    better_text = f"{satellite_count} satellites" if satellite_count else "All satellite counts"
    title = f'Total Idle Time (Overall System Utilization): All Image Sizes\nEach cell shows 4 image sizes: {", ".join([f"{s:.3f}MB" for s in sorted_sizes])}\nTime: Maximum possible connection time - actual connection time | {better_text}'
    
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
    
    # Save the plot with professional naming convention
    if satellite_count is not None:
        output_path = f"combined_total_idle_matrix_visibility_{satellite_count}sats.png"
    else:
        output_path = "combined_total_idle_matrix_visibility.png"
    
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"\n✅ Combined total idle matrix (visibility) saved: {output_path}")
    
    # Print summary showing worst total idle performance for each policy across all image sizes
    print(f"\n=== COMBINED TOTAL IDLE TIME SUMMARY (VISIBILITY) ===")
    print(f"{'Policy':<15} {'Image Size':<12} {'Worst Strategy':<20} {'Idle Time (s)':<15} {'Idle %':<12}")
    print("-" * 90)
    
    for policy_idx, policy in enumerate(policies):
        for img_idx, img_size in enumerate(sorted_sizes):
            row_idx = policy_idx * rows_per_policy + img_idx
            row_idles = total_idle_matrix[row_idx, :]
            worst_strategy_idx = np.argmax(row_idles)  # Highest idle = worst
            worst_strategy = strategies[worst_strategy_idx]
            worst_idle = row_idles[worst_strategy_idx]
            worst_time = total_idle_counts_matrix[row_idx, worst_strategy_idx]
            
            print(f"{policy.upper():<15} {img_size:>7.3f} MB   {worst_strategy:<20} {int(worst_time):<15} {worst_idle:>8.1f}%")

def main():
    parser = argparse.ArgumentParser(description='Generate combined total idle time matrix (overall system utilization) using visibility logs across image sizes')
    parser.add_argument('base_folder', help='Path to folder containing multiple analysis folders')
    parser.add_argument('--sats', type=int, help='Satellite count to filter by (e.g., 1, 50, 100, 200)')
    
    args = parser.parse_args()
    
    generate_combined_total_idle_matrix_visibility(args.base_folder, args.sats)

if __name__ == "__main__":
    main()