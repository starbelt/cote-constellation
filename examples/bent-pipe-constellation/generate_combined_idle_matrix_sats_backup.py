#!/usr/bin/env python3
"""Generate combined idle time matrix across all image sizes"""

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

def steps_to_time_string(steps):
    """Convert timesteps (seconds) to hh:mm:ss format"""
    hours = steps // 3600
    minutes = (steps % 3600) // 60
    seconds = steps % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

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

def calculate_idle_time_for_policy(policy_dir):
    """Calculate total idle time: hogging idle (connected with empty buffers) + spacing idle (no connections)"""
    hogging_idle_timesteps = 0
    total_connected_timesteps = 0
    total_simulation_timesteps = 0
    
    try:
        # Find all buffer files and tx-rx connection file
        buffer_files = [f for f in os.listdir(policy_dir) if f.startswith('meas-MB-buffered-sat-') and f.endswith('.csv')]
        tx_rx_file = policy_dir / "meas-downlink-tx-rx.csv"
        
        if not tx_rx_file.exists():
            print(f"   Warning: No tx-rx file found for policy")
            return 0, 0
        
        # Load connection data
        tx_rx_df = pd.read_csv(tx_rx_file)
        if len(tx_rx_df.columns) < 2:
            return 0, 0
            
        tx_rx_df = tx_rx_df.iloc[:, :2]
        tx_rx_df.columns = ["timestamp", "satellite"]
        tx_rx_df["timestamp"] = pd.to_datetime(tx_rx_df["timestamp"])
        
        # Calculate total simulation timesteps from any buffer file
        if buffer_files:
            first_buffer_path = policy_dir / buffer_files[0]
            first_buffer_df = pd.read_csv(first_buffer_path)
            total_simulation_timesteps = len(first_buffer_df)
        
        # Process each satellite's buffer data for hogging idle
        for buffer_file in buffer_files:
            buffer_path = policy_dir / buffer_file
            
            try:
                # Extract satellite ID from filename: meas-MB-buffered-sat-0060518000.csv -> 60518000-0
                sat_id_match = re.search(r'meas-MB-buffered-sat-(\d+)\.csv', buffer_file)
                if not sat_id_match:
                    continue
                    
                sat_id_padded = sat_id_match.group(1)  # e.g., "0060518000"
                sat_id_base = sat_id_padded.lstrip('0')  # Remove leading zeros -> "60518000"
                satellite_id = f"{sat_id_base}-0"  # Format for tx-rx lookup -> "60518000-0"
                
                # Get connection timestamps for this satellite
                connected_entries = tx_rx_df[tx_rx_df["satellite"] == satellite_id]
                if connected_entries.empty:
                    continue
                
                # Load buffer data
                buffer_df = pd.read_csv(buffer_path)
                if len(buffer_df) < 2 or len(buffer_df.columns) < 2:
                    continue
                    
                buffer_df = buffer_df.iloc[:, :2]
                buffer_df.columns = ["timestamp", "buffer_mb"]
                buffer_df["timestamp"] = pd.to_datetime(buffer_df["timestamp"])
                buffer_df["buffer_mb"] = pd.to_numeric(buffer_df["buffer_mb"], errors='coerce').fillna(0)
                
                # Count hogging idle timesteps: connected AND buffer = 0
                satellite_hogging_idle = 0
                satellite_connected = 0
                
                for _, conn_row in connected_entries.iterrows():
                    conn_time = conn_row["timestamp"]
                    satellite_connected += 1
                    
                    # Find buffer level at this timestamp
                    buffer_at_time = buffer_df[buffer_df["timestamp"] == conn_time]["buffer_mb"]
                    
                    if len(buffer_at_time) > 0 and buffer_at_time.iloc[0] <= 0.001:  # Small threshold for floating point
                        satellite_hogging_idle += 1
                
                hogging_idle_timesteps += satellite_hogging_idle
                total_connected_timesteps += satellite_connected
                
            except Exception as e:
                continue
    
    except Exception as e:
        print(f"   Error calculating idle time: {e}")
        return 0, 0
    
    # Calculate spacing idle time (timesteps with no connections)
    spacing_idle_timesteps = total_simulation_timesteps - total_connected_timesteps
    
    # Total idle = hogging idle + spacing idle
    total_idle_timesteps = hogging_idle_timesteps + spacing_idle_timesteps
    
    return total_idle_timesteps, total_simulation_timesteps

def calculate_idle_for_strategy(strategy_folder):
    """Calculate idle time percentages and absolute counts for all policies in a strategy"""
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
                # Calculate idle time using connection and buffer analysis
                total_idle, total_simulation = calculate_idle_time_for_policy(policy_dir)
                
                # Calculate idle percentage based on total simulation time
                if total_simulation > 0:
                    idle_percentage = (total_idle / total_simulation) * 100
                else:
                    idle_percentage = 0
                
                results[policy] = idle_percentage
                idle_data[policy] = total_idle  # Store absolute idle timesteps
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
    return None  # If no satellite count found, return None (old format)

def generate_combined_idle_matrix(base_folder, satellite_count=None):
    """Generate combined idle time matrix for specific satellite count (image size comparison only)"""
    base_path = Path(base_folder)
    
    if not base_path.exists():
        print(f"❌ Base folder not found: {base_folder}")
        return
    
    constellation_info = f" ({satellite_count} satellites)" if satellite_count else ""
    print(f"=== Generating Combined Idle Time Matrix{constellation_info} ===")
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
    
    # Calculate idle time for each image size and strategy
    all_idle_data = {}
    all_timestep_data = {}
    image_sizes = []
    
    for analysis_folder in analysis_folders:
        img_size = extract_image_size_from_folder(analysis_folder.name)
        if img_size is None:
            continue
            
        image_sizes.append(img_size)
        print(f"\n🔄 Processing image size {img_size:.3f} MB...")
        
        idle_data = {}
        timestep_data = {}
        
        for strategy in strategies:
            strategy_folder = analysis_folder / strategy
            
            if strategy_folder.exists():
                idle_data[strategy], timestep_data[strategy] = calculate_idle_for_strategy(strategy_folder)
                print(f"   ✅ {strategy}: Processed")
            else:
                print(f"   ❌ {strategy}: Not found")
                idle_data[strategy] = {policy: 0 for policy in policies}
                timestep_data[strategy] = {policy: 0 for policy in policies}
        
        all_idle_data[img_size] = idle_data
        all_timestep_data[img_size] = timestep_data
    
    if not image_sizes:
        print("❌ No valid analysis folders found")
        return
    
    # Create combined matrix (policies × strategies, with each cell showing all 4 image sizes)
    # We'll use a larger matrix where each "cell" is actually 4 sub-cells vertically stacked
    rows_per_policy = len(image_sizes)  # 4 image sizes per policy
    total_rows = len(policies) * rows_per_policy
    
    idle_matrix = np.zeros((total_rows, len(strategies)))
    timestep_matrix = np.zeros((total_rows, len(strategies)))
    
    # Fill the matrix: each policy gets 4 rows (one per image size)
    for policy_idx, policy in enumerate(policies):
        for img_idx, img_size in enumerate(image_sizes):
            row_idx = policy_idx * rows_per_policy + img_idx
            
            for strategy_idx, strategy in enumerate(strategies):
                idle_percentage = all_idle_data[img_size][strategy][policy]
                idle_timesteps = all_timestep_data[img_size][strategy][policy]
                
                idle_matrix[row_idx, strategy_idx] = idle_percentage
                timestep_matrix[row_idx, strategy_idx] = idle_timesteps
    
    # Create the plot with adjusted size for the larger matrix
    fig, ax = plt.subplots(figsize=(16, 14))
    
    # Use Reds colormap (higher idle time = worse = darker red)
    cmap = 'Reds'
    better_text = "Lower Values = Better Performance (Less Wasted Time)"
    
    # Create the heatmap using imshow
    im = ax.imshow(idle_matrix, cmap=cmap, aspect='auto')
    
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
    max_value = np.max(idle_matrix)
    min_value = np.min(idle_matrix)
    cbar = plt.colorbar(im, ax=ax, shrink=0.8)
    cbar.set_label('Idle Time (%)', rotation=270, labelpad=20, fontsize=12, fontweight='bold')
    cbar.ax.tick_params(labelsize=10)
    
    # Add text annotations with values - show idle time and percentage
    for policy_idx, policy in enumerate(policies):
        for img_idx, img_size in enumerate(image_sizes):
            row_idx = policy_idx * rows_per_policy + img_idx
            
            for strategy_idx, strategy in enumerate(strategies):
                idle_timesteps = timestep_matrix[row_idx, strategy_idx]
                idle_pct = idle_matrix[row_idx, strategy_idx]
                
                # Format text showing idle time and percentage
                idle_time = steps_to_time_string(int(idle_timesteps))
                value_text = f'{idle_time}\n{idle_pct:.1f}%'
                    
                text = ax.text(strategy_idx, row_idx, value_text, ha="center", va="center", 
                             color='black', fontweight='bold', fontsize=9)
    
    # Create comprehensive title
    constellation_title = f" ({satellite_count} Satellite Constellation)" if satellite_count else ""
    title = f'Idle Time (Wasted Connection Time){constellation_title}: All Image Sizes\nEach cell shows 4 image sizes: {", ".join([f"{s:.3f}MB" for s in image_sizes])}\nTime format: hh:mm:ss | {better_text}'
    
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
    
    # Save the plot with satellite count in filename
    if satellite_count is not None:
        output_filename = f'combined_idle_matrix_{satellite_count}sats.png'
    else:
        output_filename = 'combined_idle_matrix.png'
    output_path = base_path.parent / output_filename
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"\n✅ Combined idle matrix saved: {output_path}")
    
    # Print summary showing worst idle performance for each policy across all image sizes
    print(f"\n=== COMBINED IDLE TIME SUMMARY ===")
    print(f"{'Policy':<15} {'Image Size':<12} {'Worst Strategy':<20} {'Idle Steps':<12} {'Idle %':<12}")
    print("-" * 85)
    
    for policy_idx, policy in enumerate(policies):
        for img_idx, img_size in enumerate(image_sizes):
            row_idx = policy_idx * rows_per_policy + img_idx
            row_idles = idle_matrix[row_idx, :]
            worst_strategy_idx = np.argmax(row_idles)  # Highest idle = worst
            worst_strategy = strategies[worst_strategy_idx]
            worst_idle = row_idles[worst_strategy_idx]
            worst_timesteps = timestep_matrix[row_idx, worst_strategy_idx]
            
            print(f"{policy.upper():<15} {img_size:>7.3f} MB   {worst_strategy:<20} {worst_timesteps:>8.0f}     {worst_idle:>8.1f}%")

def main():
    parser = argparse.ArgumentParser(description='Generate combined idle time matrix across image sizes for specific satellite count')
    parser.add_argument('base_folder', help='Path to folder containing multiple analysis folders')
    parser.add_argument('--sats', type=int, help='Satellite count to filter by (e.g., 1, 50, 100, 200)')
    args = parser.parse_args()
    
    generate_combined_idle_matrix(args.base_folder, args.sats)

if __name__ == "__main__":
    main()