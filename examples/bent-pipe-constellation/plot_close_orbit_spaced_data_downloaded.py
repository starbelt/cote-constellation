#!/usr/bin/env python3
"""
Create stacked bar charts showing TOTAL DATA DOWNLOADED by constellation size and policy.
CLOSE-ORBIT-SPACED STRATEGY - 25 CLUSTERS

This shows total data downloaded to understand performance across constellation sizes.

X-axis: Constellation sizes (1, 25, 50, 100, 200)
Y-axis: Total data downloaded (GB)
Stacks: Each bar divided by 4 link policies (sticky, fifo, roundrobin, random)

One chart per image size.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import zipfile
from pathlib import Path
import re

# Configuration - use absolute paths
SCRIPT_DIR = Path(__file__).parent.absolute()

def scan_close_orbit_spaced_configurations(search_dirs=['results/base results 2']):
    """Scan for close-orbit-spaced configurations"""
    configs = []
    
    # Scan multiple directories
    for search_dir in search_dirs:
        search_path = Path(search_dir)
        if not search_path.exists():
            print(f"⚠️  Directory not found: {search_dir}")
            continue
        
        for folder in search_path.glob('constellation_analysis_*'):
            if not folder.is_dir():
                continue
            
            # Parse folder name: constellation_analysis_YYYYMMDD_HHMMSS_IMAGESIZE_NUMSATS
            match = re.match(r'constellation_analysis_\d{8}_\d{6}_(\d+)_(\d+)', folder.name)
            if match:
                image_size_kb = int(match.group(1))
                num_sats = int(match.group(2))
                
                # Check for close-orbit-spaced strategy only
                strategy_path = folder / 'close-orbit-spaced' / 'simulation_logs.zip'
                if strategy_path.exists():
                    configs.append({
                        'folder': folder,
                        'image_size_kb': image_size_kb,
                        'num_sats': num_sats,
                        'zip_path': strategy_path
                    })
    
    return pd.DataFrame(configs)

def get_data_downloaded(zip_path, policy='fifo'):
    """Get total data downloaded from visibility log"""
    try:
        with zipfile.ZipFile(zip_path, 'r') as zipf:
            with zipf.open(f'{policy}/visibility_log.csv') as f:
                df = pd.read_csv(f)
        
        # Sum all downloaded data in MB, convert to GB
        total_downloaded_mb = df['downloaded_mb'].sum()
        total_downloaded_gb = total_downloaded_mb / 1024.0
        
        return total_downloaded_gb
        
    except Exception as e:
        print(f"  ⚠️  Error reading {zip_path}/{policy}: {e}")
        return 0.0

def create_close_orbit_spaced_charts():
    """Create stacked bar charts - one per image size, close-orbit-spaced only"""
    
    print("="*110)
    print("=" * 30 + " CLOSE-ORBIT-SPACED STRATEGY: DATA DOWNLOADED STACKED BAR CHARTS")
    print("25 Clusters Configuration | Stacked by Policy")
    print("="*110)
    print()
    
    print("Scanning for close-orbit-spaced configurations (25 clusters + base results)...")
    configs_df = scan_close_orbit_spaced_configurations()
    
    if len(configs_df) == 0:
        print("❌ No close-orbit-spaced configurations found!")
        return
    
    print(f"Found {len(configs_df)} close-orbit-spaced configurations")
    print()
    
    # Collect all data
    results = []
    
    # Group by image_size and num_sats
    grouped = configs_df.groupby(['image_size_kb', 'num_sats'])
    
    policies = ['sticky', 'fifo', 'roundrobin', 'random']
    
    print("Calculating data downloaded...")
    for (image_size_kb, num_sats), group in grouped:
        image_size_mb = image_size_kb / 1000.0
        
        for policy in policies:
            row = group.iloc[0]
            data_gb = get_data_downloaded(row['zip_path'], policy)
            
            results.append({
                'image_size_mb': image_size_mb,
                'policy': policy,
                'num_sats': num_sats,
                'orbital_spacing_deg': 360.0 / 25,  # 25 orbital positions
                'data_downloaded_gb': data_gb
            })
    
    results_df = pd.DataFrame(results)
    
    # Save raw data in centralized constellation_analysis directory
    output_dir = SCRIPT_DIR / "constellation_analysis" / "close_orbit_spaced_charts"
    output_dir.mkdir(parents=True, exist_ok=True)
    results_df.to_csv(output_dir / 'close_orbit_spaced_data_downloaded.csv', index=False)
    print(f"✅ Saved: {output_dir / 'close_orbit_spaced_data_downloaded.csv'}")
    print()
    
    # Create charts
    create_charts(results_df, output_dir)
    
    return results_df

def create_charts(results_df, output_dir):
    """Create stacked bar charts per image size (close-orbit-spaced only)"""
    
    # Get unique values
    image_sizes = sorted(results_df['image_size_mb'].unique())
    policies = ['sticky', 'fifo', 'roundrobin', 'random']
    
    # Color scheme by policy (4 distinct colors for stacks)
    policy_colors = {
        'sticky': '#E63946',      # Red
        'fifo': '#2E86AB',        # Blue
        'roundrobin': '#06A77D',  # Green
        'random': '#F77F00'       # Orange
    }
    
    # Create one chart per image size
    for image_size in image_sizes:
        print(f"Creating close-orbit-spaced data downloaded chart for {image_size} MB...")
        
        subset = results_df[results_df['image_size_mb'] == image_size]
        
        if len(subset) == 0:
            continue
        
        # Get satellite counts for this image size
        sat_counts = sorted(subset['num_sats'].unique())
        
        # Create figure
        fig, ax = plt.subplots(1, 1, figsize=(14, 10))
        
        # Prepare data structure for stacked bars
        bar_width = 0.7
        x_positions = np.arange(len(sat_counts))
        
        # Build stacked bars
        for x_idx, sat_count in enumerate(sat_counts):
            # Calculate cluster info
            if sat_count == 1:
                cluster_info = "1 sat"
            elif sat_count == 25:
                cluster_info = "25 clusters × 1"
            elif sat_count == 50:
                cluster_info = "25 clusters × 2"
            elif sat_count == 100:
                cluster_info = "25 clusters × 4"
            elif sat_count == 200:
                cluster_info = "25 clusters × 8"
            else:
                cluster_info = f"{sat_count} sats"
            
            # Get data for all policies for this sat_count
            bottom = 0
            for policy in policies:
                data = subset[
                    (subset['policy'] == policy) & 
                    (subset['num_sats'] == sat_count)
                ]
                
                if len(data) > 0:
                    value = data['data_downloaded_gb'].values[0]
                else:
                    value = 0
                
                # Draw this segment of the stack
                ax.bar(x_positions[x_idx], value, bar_width, bottom=bottom, 
                      color=policy_colors[policy], 
                      edgecolor='white', linewidth=2,
                      label=policy.upper() if x_idx == 0 else "")
                
                # Add text label in the center of this stack segment
                if value > 0:
                    text_y = bottom + value / 2
                    text = f'{value:.1f}'
                    
                    ax.text(x_positions[x_idx], text_y, text, 
                           ha='center', va='center',
                           fontsize=8, fontweight='bold',
                           color='white',
                           bbox=dict(boxstyle='round,pad=0.3', 
                                    facecolor='black', 
                                    edgecolor='none',
                                    alpha=0.7))
                
                bottom += value
            
            # Add total on top of bar
            if bottom > 0:
                total_text = f'{bottom:.1f} GB'
                ax.text(x_positions[x_idx], bottom * 1.03, total_text, 
                       ha='center', va='bottom',
                       fontsize=10, fontweight='bold',
                       color='black')
            
            # Add cluster info annotation below bar
            max_y = subset.groupby('num_sats')['data_downloaded_gb'].sum().max()
            spacing_offset = -max(0.5, max_y * 0.05)
            ax.text(x_positions[x_idx], spacing_offset, cluster_info, 
                   ha='center', va='top',
                   fontsize=9, fontweight='bold',
                   color='#555')
        
        # Set x-axis labels
        ax.set_xticks(x_positions)
        ax.set_xticklabels([f'{sat}' for sat in sat_counts], fontsize=11, fontweight='bold')
        ax.set_xlabel('Number of Satellites', fontsize=13, fontweight='bold')
        
        # Y-axis
        ax.set_ylabel('Data Downloaded (GB)', fontsize=13, fontweight='bold')
        
        # Set y limits with padding
        max_y = subset.groupby('num_sats')['data_downloaded_gb'].sum().max()
        min_offset = max(1.0, max_y * 0.08)
        ax.set_ylim(-min_offset, max_y * 1.18)
        
        # Title
        ax.set_title(f'Close-Orbit-Spaced (25 Clusters): Data Downloaded by Satellite Count\n{image_size} MB Images',
                    fontsize=15, fontweight='bold', pad=10)
        
        # Grid
        ax.grid(True, alpha=0.3, linestyle='--', axis='y')
        ax.set_axisbelow(True)
        
        # Legend
        ax.legend(title='Link Policy', fontsize=11, title_fontsize=12, 
                  loc='upper left', framealpha=0.95, edgecolor='black')
        
        plt.tight_layout()
        
        # Save
        filename = f'close_orbit_spaced_data_downloaded_{image_size}mb.png'
        output_file = output_dir / filename
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"✅ Saved: {output_file}")
        plt.close()
    
    print()
    print("="*110)
    print("✅ CLOSE-ORBIT-SPACED DATA DOWNLOADED STACKED BAR CHARTS COMPLETE!")
    print("="*110)
    print()
    print("Chart Structure:")
    print("  X-AXIS: Constellation sizes (1, 25, 50, 100, 200)")
    print("          Cluster configuration shown below each bar")
    print()
    print("  Y-AXIS: Data Downloaded (GB) - total data retrieved")
    print()
    print("  STACKS: Each bar divided by 4 policies:")
    print("    🔴 Red    = STICKY")
    print("    🔵 Blue   = FIFO")
    print("    🟢 Green  = ROUNDROBIN")
    print("    🟠 Orange = RANDOM")
    print()
    print(f"  RESULT: {len(image_sizes)} chart(s) (one per image size)")

if __name__ == '__main__':
    import os
    
    # Change to script directory
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    results_df = create_close_orbit_spaced_charts()
    
    if results_df is not None:
        print()
        print("✨ Close-orbit-spaced data downloaded stacked bar charts complete!")
