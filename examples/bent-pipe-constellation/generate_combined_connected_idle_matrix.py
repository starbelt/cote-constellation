#!/usr/bin/env python3
"""Generate combined connected idle time matrix (satellites wasting link time) across all image sizes"""

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

def calculate_connected_idle_from_visibility_log(strategy_folder):
    """Calculate connected idle time from visibility_log.csv"""
    policies = ["sticky", "roundrobin", "fifo", "random"]
    results = {}
    idle_data = {}
    total_data = {}  # Add total connected events tracking
    
    simulation_logs_zip = strategy_folder / "simulation_logs.zip"
    
    if not simulation_logs_zip.exists():
        print(f"   ❌ No simulation logs found")
        return {policy: 0 for policy in policies}, {policy: 0 for policy in policies}
    
    # Read configuration for image size
    config = read_config_from_zip(simulation_logs_zip)
    image_size = config.get('image_size', 0.027)
    
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
                    
                    # Calculate connected idle events: connected=1 AND buffer_mb <= 0.001
                    connected_idle_events = df[(df['connected'] == 1) & (df['buffer_mb'] <= 0.001)]
                    
                    # Count total connection events for percentage calculation
                    total_connected_events = df[df['connected'] == 1]
                    
                    if len(total_connected_events) > 0:
                        connected_idle_percentage = (len(connected_idle_events) / len(total_connected_events)) * 100
                    else:
                        connected_idle_percentage = 0
                    
                    results[policy] = connected_idle_percentage
                    idle_data[policy] = len(connected_idle_events)  # Store absolute count
                    total_data[policy] = len(total_connected_events)  # Store total connected events
                    
                    # Calculate active connected events for display
                    active_connected = len(total_connected_events) - len(connected_idle_events)
                    print(f"   {policy}: {active_connected}/{len(total_connected_events)} active connected events = {connected_idle_percentage:.1f}% connected idle")
                    
                except Exception as e:
                    print(f"   Error processing {policy}: {e}")
                    results[policy] = 0
                    idle_data[policy] = 0
                    total_data[policy] = 0  # Initialize total connected events
            else:
                print(f"   ⚠️  {policy}: No visibility log found")
                results[policy] = 0
                idle_data[policy] = 0
                total_data[policy] = 0  # Initialize total connected events
    
    return results, idle_data, total_data

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

def generate_combined_connected_idle_matrix(base_folder, satellite_count=None):
    """Generate connected idle time matrix for specific satellite count"""
    base_path = Path(base_folder)
    
    if not base_path.exists():
        print(f"❌ Base folder not found: {base_folder}")
        return
    
    constellation_info = f" ({satellite_count} satellites)" if satellite_count else ""
    print(f"=== Generating Connected Idle Time Matrix{constellation_info} ===")
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
    all_total_counts = {}  # Add total connected events storage
    
    for size in sorted_sizes:
        folder = size_to_folders[size][0]  # Use first (should be only) folder for this size
        print(f"\n🔄 Processing image size {size:.3f} MB...")
        
        data[size] = {}
        all_idle_counts[size] = {}
        all_total_counts[size] = {}  # Initialize total counts for this size
        
        for strategy in strategies:
            strategy_folder = folder / strategy
            
            if strategy_folder.exists():
                idle_percentages, idle_counts, total_counts = calculate_connected_idle_from_visibility_log(strategy_folder)
                data[size][strategy] = idle_percentages
                all_idle_counts[size][strategy] = idle_counts
                all_total_counts[size][strategy] = total_counts  # Store total counts
                print(f"   ✅ {strategy}: Processed")
            else:
                print(f"   ❌ {strategy}: Not found")
                data[size][strategy] = {policy: 0 for policy in policies}
                all_idle_counts[size][strategy] = {policy: 0 for policy in policies}
                all_total_counts[size][strategy] = {policy: 0 for policy in policies}  # Initialize total counts
    
    # Create single comprehensive matrix
    rows_per_policy = len(sorted_sizes)
    total_rows = len(policies) * rows_per_policy
    
    # Create matrices for visualization
    connected_idle_matrix = np.zeros((total_rows, len(strategies)))
    connected_idle_counts_matrix = np.zeros((total_rows, len(strategies)))
    total_connected_matrix = np.zeros((total_rows, len(strategies)))  # Add total connected events matrix
    
    # Fill matrices
    for policy_idx, policy in enumerate(policies):
        for size_idx, size in enumerate(sorted_sizes):
            row_idx = policy_idx * rows_per_policy + size_idx
            
            for strategy_idx, strategy in enumerate(strategies):
                connected_idle_matrix[row_idx, strategy_idx] = data[size][strategy][policy]
                connected_idle_counts_matrix[row_idx, strategy_idx] = all_idle_counts[size][strategy][policy]
                total_connected_matrix[row_idx, strategy_idx] = all_total_counts[size][strategy][policy]  # Fill total connected events
    
    # Create comprehensive visualization
    plt.figure(figsize=(16, 12))
    ax = plt.gca()
    
    # Import color utilities for custom colormap
    from matplotlib.colors import BoundaryNorm
    import matplotlib.colors as mcolors
    
    # Create custom colormap for connected idle (red gradient as this is "bad" performance)
    # Define boundaries for color mapping (0-100% range)
    boundaries = np.linspace(0, 100, 11)  # 0, 10, 20, ..., 100
    colors = [
        '#ffffff',  # White (0% - best performance)
        '#ffe6e6',  # Very light red (0-10%)
        '#ffcccc',  # Light red (10-20%)
        '#ffb3b3',  # Light-medium red (20-30%)
        '#ff9999',  # Medium red (30-40%)
        '#ff8080',  # Medium-dark red (40-50%)
        '#ff6666',  # Dark red (50-60%)
        '#ff4d4d',  # Darker red (60-70%)
        '#ff3333',  # Very dark red (70-80%)
        '#ff1a1a',  # Almost darkest red (80-90%)
        '#ff0000'   # Bright red (90-100% - worst performance)
    ]
    cmap = mcolors.ListedColormap(colors)
    norm = BoundaryNorm(boundaries, cmap.N)
    
    # Create heatmap with custom colormap
    im = ax.imshow(connected_idle_matrix, cmap=cmap, aspect='auto', norm=norm)
    
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
    max_value = np.max(connected_idle_matrix)
    min_value = np.min(connected_idle_matrix)
    cbar = plt.colorbar(im, ax=ax, shrink=0.8)
    cbar.set_label('Connected Idle Time (%)', rotation=270, labelpad=20, fontsize=12, fontweight='bold')
    cbar.ax.tick_params(labelsize=10)
    
    # Add text annotations with values - show active/total format
    for policy_idx, policy in enumerate(policies):
        for img_idx, img_size in enumerate(sorted_sizes):
            row_idx = policy_idx * rows_per_policy + img_idx
            
            for strategy_idx, strategy in enumerate(strategies):
                connected_idle_count = connected_idle_counts_matrix[row_idx, strategy_idx]
                total_connected_count = total_connected_matrix[row_idx, strategy_idx]
                connected_idle_pct = connected_idle_matrix[row_idx, strategy_idx]
                
                # Calculate active connected events (total - idle)
                active_connected = total_connected_count - connected_idle_count
                
                # Format text showing active/total connected events and idle percentage
                value_text = f'{int(active_connected)}/{int(total_connected_count)}\n{connected_idle_pct:.1f}%'
                    
                text = ax.text(strategy_idx, row_idx, value_text, ha="center", va="center", 
                             color='black', fontweight='bold', fontsize=9)
    
    # Create comprehensive title
    better_text = f"{satellite_count} satellites" if satellite_count else "All satellite counts"
    title = f'Connected Idle Time (Active Connected / Total Connected): All Image Sizes\nEach cell shows 4 image sizes: {", ".join([f"{s:.3f}MB" for s in sorted_sizes])}\nEvents: Connected with buffer ≤ 0.001 MB | {better_text}'
    
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
    
    # Save the plot to constellation_analysis directory
    script_dir = Path(__file__).parent
    output_dir = script_dir / "constellation_analysis" / "connected_idle_matrix"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if satellite_count is not None:
        output_path = output_dir / f"combined_connected_idle_matrix_{satellite_count}sats.png"
    else:
        output_path = output_dir / "combined_connected_idle_matrix.png"
    
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"\n✅ Combined connected idle matrix saved: {output_path}")
    
    # Print summary showing worst connected idle performance for each policy across all image sizes
    print(f"\n=== COMBINED CONNECTED IDLE TIME SUMMARY ===")
    print(f"{'Policy':<15} {'Image Size':<12} {'Worst Strategy':<20} {'Idle Events':<15} {'Idle %':<12}")
    print("-" * 90)
    
    for policy_idx, policy in enumerate(policies):
        for img_idx, img_size in enumerate(sorted_sizes):
            row_idx = policy_idx * rows_per_policy + img_idx
            row_idles = connected_idle_matrix[row_idx, :]
            worst_strategy_idx = np.argmax(row_idles)  # Highest idle = worst
            worst_strategy = strategies[worst_strategy_idx]
            worst_idle = row_idles[worst_strategy_idx]
            worst_count = connected_idle_counts_matrix[row_idx, worst_strategy_idx]
            
            print(f"{policy.upper():<15} {img_size:>7.3f} MB   {worst_strategy:<20} {int(worst_count):<15} {worst_idle:>8.1f}%")

def main():
    parser = argparse.ArgumentParser(description='Generate combined connected idle time matrix (satellites wasting link time) across image sizes')
    parser.add_argument('base_folder', help='Path to folder containing multiple analysis folders')
    parser.add_argument('--sats', type=int, help='Satellite count to filter by (e.g., 1, 50, 100, 200)')
    
    args = parser.parse_args()
    
    generate_combined_connected_idle_matrix(args.base_folder, args.sats)

if __name__ == "__main__":
    main()