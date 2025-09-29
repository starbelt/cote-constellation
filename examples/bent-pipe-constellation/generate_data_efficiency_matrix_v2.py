#!/usr/bin/env python3
"""Generate data efficiency matrix using corrected calculation"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import zipfile
import tempfile
from pathlib import Path
import argparse
import os

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
        
        print(f"   Found {len(buffer_files)} buffer files")
        
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
                print(f"   Warning: Error processing {buffer_file}: {e}")
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
    
    simulation_logs_zip = strategy_folder / "simulation_logs.zip"
    
    if not simulation_logs_zip.exists():
        print(f"   ❌ No simulation logs found")
        return {policy: 0 for policy in policies}
    
    # Read configuration for image size
    config = read_config_from_zip(simulation_logs_zip)
    image_size = config.get('image_size', 0.289)
    
    print(f"   📊 Image size: {image_size} MB")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        with zipfile.ZipFile(simulation_logs_zip, 'r') as zipf:
            zipf.extractall(temp_path)
        
        for policy in policies:
            policy_dir = temp_path / policy
            
            if policy_dir.exists():
                print(f"   📁 Processing {policy}...")
                
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
                
                print(f"     📈 Accumulated: {total_accumulated:.1f} MB")
                print(f"     📉 Downloaded: {total_downloaded:.1f} MB") 
                print(f"     🎯 Efficiency: {efficiency:.1f}%")
            else:
                results[policy] = 0
                download_data[policy] = 0
                print(f"   ❌ Policy directory not found: {policy}")
    
    return results, download_data

def generate_efficiency_matrix(analysis_folder):
    """Generate data efficiency matrix for all strategies and policies"""
    analysis_path = Path(analysis_folder)
    
    if not analysis_path.exists():
        print(f"❌ Analysis folder not found: {analysis_folder}")
        return
    
    print(f"=== Generating Data Efficiency Matrix ===")
    print(f"📁 Analysis folder: {analysis_folder}")
    
    strategies = ["close-spaced", "frame-spaced", "orbit-spaced", "close-orbit-spaced"]
    policies = ["sticky", "roundrobin", "fifo", "random"]
    
    # Calculate efficiency for each strategy
    efficiency_data = {}
    download_data = {}
    
    # Variables to track totals for title
    total_buffered_mb = 0
    image_size_mb = 0
    
    for strategy in strategies:
        print(f"\n🔄 Processing {strategy}...")
        strategy_folder = analysis_path / strategy
        
        if strategy_folder.exists():
            strategy_results, strategy_downloads = calculate_efficiency_for_strategy(strategy_folder)
            efficiency_data[strategy] = strategy_results
            download_data[strategy] = strategy_downloads
            
            # Get image size and calculate total buffered for title (use first strategy's data)
            if strategy == strategies[0]:
                simulation_logs_zip = strategy_folder / "simulation_logs.zip"
                if simulation_logs_zip.exists():
                    config = read_config_from_zip(simulation_logs_zip)
                    image_size_mb = config.get('image_size', 0.289)
                    
                    # Calculate total buffered across all strategies and policies
                    with tempfile.TemporaryDirectory() as temp_dir:
                        temp_path = Path(temp_dir)
                        with zipfile.ZipFile(simulation_logs_zip, 'r') as zipf:
                            zipf.extractall(temp_path)
                        
                        # Use sticky policy as representative for total calculation
                        policy_dir = temp_path / "sticky"
                        if policy_dir.exists():
                            total_buffered_mb = calculate_total_data_accumulated(policy_dir, image_size_mb)
        else:
            print(f"   ❌ Strategy folder not found: {strategy}")
            efficiency_data[strategy] = {policy: 0 for policy in policies}
            download_data[strategy] = {policy: 0 for policy in policies}
    
    # Create efficiency matrix (policies on Y-axis, strategies on X-axis to match other matrices)
    efficiency_matrix = np.zeros((len(policies), len(strategies)))
    download_matrix = np.zeros((len(policies), len(strategies)))
    
    for i, policy in enumerate(policies):
        for j, strategy in enumerate(strategies):
            efficiency_matrix[i, j] = efficiency_data[strategy][policy]
            download_matrix[i, j] = download_data[strategy][policy]
    
    # Create the plot with same styling as spacing matrices
    fig, ax = plt.subplots(figsize=(12, 10))
    
    # Use Greens colormap like download matrix (higher efficiency = better = darker green)
    cmap = 'Greens'
    better_text = "Higher Values = Better Performance"
    
    # Create the heatmap using imshow (same as spacing matrices)
    im = ax.imshow(efficiency_matrix, cmap=cmap, aspect='auto')
    
    # Set ticks and labels with same styling
    policy_labels = [p.upper() for p in policies]  # Match the uppercase style
    strategy_labels = [s.replace('-', '-').title() for s in strategies]  # Clean up strategy names
    
    ax.set_xticks(np.arange(len(strategies)))
    ax.set_yticks(np.arange(len(policies)))
    ax.set_xticklabels(strategy_labels, fontsize=12, fontweight='bold')
    ax.set_yticklabels(policy_labels, fontsize=12, fontweight='bold')
    
    # Add colorbar with same styling
    max_value = np.max(efficiency_matrix)
    min_value = np.min(efficiency_matrix)
    cbar = plt.colorbar(im, ax=ax, shrink=0.8)
    cbar.set_label('Download Efficiency (%)', rotation=270, labelpad=20, fontsize=12, fontweight='bold')
    cbar.ax.tick_params(labelsize=10)
    
    # Add text annotations with values (same black text style as spacing matrices)
    for i in range(len(policies)):
        for j in range(len(strategies)):
            download_gb = download_matrix[i, j] / 1000  # Convert MB to GB
            efficiency_pct = efficiency_matrix[i, j]
            
            # Format like spacing matrices - show both metrics clearly with 3 decimal precision
            if download_gb >= 1000:  # Use TB for very large values
                value_text = f'{download_gb/1000:.3f} TB\n({efficiency_pct:.1f}%)'
            elif download_gb >= 1:
                value_text = f'{download_gb:.3f} GB\n({efficiency_pct:.1f}%)'
            else:
                value_text = f'{download_matrix[i, j]:.0f} MB\n({efficiency_pct:.1f}%)'
                
            text = ax.text(j, i, value_text, ha="center", va="center", 
                         color='black', fontweight='bold', fontsize=10)
    
    # Create comprehensive title with image size and total buffered data (match spacing matrix style)
    total_buffered_gb = total_buffered_mb / 1000  # Convert to GB for readability
    if total_buffered_gb >= 1000:
        buffered_str = f'{total_buffered_gb/1000:.1f} TB'
    else:
        buffered_str = f'{total_buffered_gb:.1f} GB'
    
    title = f'Data Download Efficiency by Strategy × Policy\nImage Size: {image_size_mb:.3f} MB, Total Buffered: {buffered_str} (across 50 satellites)\n{better_text}'
    
    # Titles and labels with same styling as spacing matrices
    ax.set_title(title, fontsize=16, fontweight='bold', pad=25)
    ax.set_xlabel('Spacing Strategy', fontsize=14, fontweight='bold')
    ax.set_ylabel('Scheduling Policy', fontsize=14, fontweight='bold')
    
    # Add grid for better readability (same as spacing matrices)
    ax.set_xticks(np.arange(len(strategies)+1)-.5, minor=True)
    ax.set_yticks(np.arange(len(policies)+1)-.5, minor=True)
    ax.grid(which="minor", color="black", linestyle='-', linewidth=2)
    ax.tick_params(which="minor", size=0)    # Rotate labels for better readability
    plt.xticks(rotation=45, ha='right')
    plt.yticks(rotation=0)
    
    plt.tight_layout()
    
    # Save the plot
    output_path = analysis_path / 'spacing_efficiency_matrix.png'
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()  # Close like spacing matrices do
    print(f"\n✅ Efficiency matrix saved: {output_path}")
    
    # Also save the raw data with proper orientation
    efficiency_df = pd.DataFrame(efficiency_matrix, 
                                index=policies, 
                                columns=strategies)
    download_df = pd.DataFrame(download_matrix, 
                              index=policies, 
                              columns=strategies)
    
    csv_path = analysis_path / 'spacing_efficiency_data.csv'
    efficiency_df.to_csv(csv_path)
    print(f"✅ Efficiency data saved: {csv_path}")
    
    download_csv_path = analysis_path / 'spacing_download_data.csv'
    download_df.to_csv(download_csv_path)
    print(f"✅ Download data saved: {download_csv_path}")
    
    # Print summary
    print(f"\n=== EFFICIENCY SUMMARY ===")
    print(f"Image Size: {image_size_mb:.3f} MB")
    if total_buffered_gb >= 1000:
        print(f"Total Buffered: {total_buffered_gb/1000:.1f} TB (across 50 satellites)")
    else:
        print(f"Total Buffered: {total_buffered_gb:.1f} GB (across 50 satellites)")
    print(f"{'Policy':<15} {'Best Strategy':<20} {'Download (GB)':<15} {'Efficiency':<12}")
    print("-" * 65)
    
    for policy in policies:
        policy_efficiencies = {}
        policy_downloads = {}
        for strategy in strategies:
            policy_efficiencies[strategy] = efficiency_data[strategy][policy]
            policy_downloads[strategy] = download_data[strategy][policy] / 1000  # Convert to GB
        
        best_strategy = max(policy_efficiencies.items(), key=lambda x: x[1])
        best_download = policy_downloads[best_strategy[0]]
        
        print(f"{policy:<15} {best_strategy[0]:<20} {best_download:>10.3f} GB {best_strategy[1]:>8.1f}%")

def main():
    parser = argparse.ArgumentParser(description='Generate data efficiency matrix')
    parser.add_argument('analysis_folder', help='Path to analysis folder containing strategy results')
    args = parser.parse_args()
    
    generate_efficiency_matrix(args.analysis_folder)

if __name__ == "__main__":
    main()