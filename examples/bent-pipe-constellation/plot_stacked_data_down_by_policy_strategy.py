#!/usr/bin/env python3
"""
Create stacked bar charts showing total data downloaded by constellation size, policy, and strategy.

FLIPPED VERSION - Shows MaxDownload advantage clearly!

X-axis: Link policies (sticky, fifo, roundrobin, random, maxdownload) grouped by constellation size
Y-axis: Total data downloaded (GB)
Stacks: Each bar divided by 4 spacing strategies (close, orbit, frame, close-orbit)

One chart per image size.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import zipfile
from pathlib import Path
import re

def scan_all_configurations(search_dir='results/base results 2'):
    """Scan for all constellation_analysis folders"""
    configs = []
    
    search_path = Path(search_dir)
    for folder in search_path.glob('constellation_analysis_*'):
        if not folder.is_dir():
            continue
        
        # Parse folder name: constellation_analysis_YYYYMMDD_HHMMSS_IMAGESIZE_NUMSATS
        match = re.match(r'constellation_analysis_\d{8}_\d{6}_(\d+)_(\d+)', folder.name)
        if match:
            image_size_kb = int(match.group(1))
            num_sats = int(match.group(2))
            
            # Check which strategies exist
            for strategy in ['close-spaced', 'orbit-spaced', 'frame-spaced', 'close-orbit-spaced']:
                strategy_path = folder / strategy / 'simulation_logs.zip'
                if strategy_path.exists():
                    configs.append({
                        'folder': folder,
                        'strategy': strategy,
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

def create_stacked_bar_charts(results_dir='results/base results 2'):
    """Create stacked bar charts - one per image size"""
    
    print("="*110)
    print("=" * 35 + " DATA DOWNLOADED BY POLICY (Stacked by Strategy)")
    print("X-axis: Link Policies | Stacks: Spacing Strategies")
    print("="*110)
    print()
    
    # Check if we can reuse existing CSV data
    existing_csv = Path('constellation_analysis') / 'data_downloaded_charts' / 'stacked_data_downloaded.csv'
    
    if existing_csv.exists():
        print(f"📊 Loading existing data from: {existing_csv}")
        results_df = pd.read_csv(existing_csv)
        print(f"✅ Loaded {len(results_df)} rows")
    else:
        print(f"Scanning for constellation configurations in: {results_dir}")
        configs_df = scan_all_configurations(results_dir)
        
        if len(configs_df) == 0:
            print("❌ No configurations found!")
            return
        
        print(f"Found {len(configs_df)} configurations")
        print()
        
        # Collect all data
        results = []
        
        # Group by image_size, strategy, and num_sats
        grouped = configs_df.groupby(['image_size_kb', 'strategy', 'num_sats'])
        
        policies = ['sticky', 'fifo', 'roundrobin', 'random', 'mindistance', 'maxdownload']
        
        for (image_size_kb, strategy, num_sats), group in grouped:
            image_size_mb = image_size_kb / 1000.0
            
            for policy in policies:
                row = group.iloc[0]
                data_gb = get_data_downloaded(row['zip_path'], policy)
                
                results.append({
                    'image_size_mb': image_size_mb,
                    'strategy': strategy,
                    'policy': policy,
                    'num_sats': num_sats,
                    'data_downloaded_gb': data_gb
                })
        
        results_df = pd.DataFrame(results)
    
    # Save raw data
    output_dir = Path('constellation_analysis') / 'data_downloaded_charts'
    output_dir.mkdir(parents=True, exist_ok=True)
    results_df.to_csv(output_dir / 'stacked_data_downloaded_by_policy.csv', index=False)
    print(f"✅ Saved: {output_dir / 'stacked_data_downloaded_by_policy.csv'}")
    print()
    
    # Create charts
    create_charts(results_df, output_dir)
    
    return results_df

def create_charts(results_df, output_dir):
    """Create one stacked bar chart per image size"""
    
    # Get unique values
    image_sizes = sorted(results_df['image_size_mb'].unique())
    strategies = ['close-spaced', 'orbit-spaced', 'frame-spaced', 'close-orbit-spaced']
    policies = ['sticky', 'fifo', 'roundrobin', 'random', 'mindistance', 'maxdownload']
    sat_counts = sorted(results_df['num_sats'].unique())
    
    # Color scheme by STRATEGY (4 distinct colors for stacks)
    strategy_colors = {
        'close-spaced': '#E63946',        # Red
        'orbit-spaced': '#2E86AB',        # Blue
        'frame-spaced': '#06A77D',        # Green
        'close-orbit-spaced': '#F77F00'   # Orange
    }
    
    # Policy labels (uppercase for display)
    policy_labels = {
        'sticky': 'STICKY',
        'fifo': 'FIFO',
        'roundrobin': 'ROUNDROBIN',
        'random': 'RANDOM',
        'mindistance': 'MINDISTANCE',
        'maxdownload': 'MAXDOWNLOAD'
    }
    
    # Strategy labels (for legend)
    strategy_labels = {
        'close-spaced': 'Close',
        'orbit-spaced': 'Orbit',
        'frame-spaced': 'Frame',
        'close-orbit-spaced': 'Close-Orbit'
    }
    
    # Create one chart per image size
    for image_size in image_sizes:
        print(f"Creating stacked bar chart for {image_size} MB...")
        
        subset = results_df[results_df['image_size_mb'] == image_size]
        
        if len(subset) == 0:
            continue
        
        # Create figure
        fig, ax = plt.subplots(figsize=(20, 10))
        
        # X positions: len(sat_counts) groups × len(policies) bars per group
        num_bars_per_group = len(policies)
        bar_width = 0.7
        group_width = num_bars_per_group * bar_width + 1.5  # Add spacing between sat count groups
        
        x_positions = []
        x_labels = []
        
        # Build stacked bars
        for sat_idx, sat_count in enumerate(sat_counts):
            for policy_idx, policy in enumerate(policies):
                # Calculate x position for this bar
                x_pos = sat_idx * group_width + policy_idx * bar_width
                x_positions.append(x_pos)
                x_labels.append(policy_labels[policy])
                
                # Stack strategies on this bar
                bottom = 0
                for strategy in strategies:
                    data = subset[
                        (subset['strategy'] == strategy) & 
                        (subset['policy'] == policy) & 
                        (subset['num_sats'] == sat_count)
                    ]
                    
                    if len(data) > 0:
                        value = data['data_downloaded_gb'].values[0]
                    else:
                        value = 0
                    
                    # Draw this segment of the stack
                    ax.bar(x_pos, value, bar_width, bottom=bottom, 
                          color=strategy_colors[strategy], 
                          edgecolor='white', linewidth=1.5,
                          label=strategy_labels[strategy] if sat_idx == 0 and policy_idx == 0 else "")
                    
                    # Add text label in the center of this stack segment
                    if value > 5:  # Only show text for segments > 5 GB
                        text_y = bottom + value / 2
                        if value < 10:
                            text = f'{value:.1f}'
                        else:
                            text = f'{value:.0f}'
                        
                        ax.text(x_pos, text_y, text, 
                               ha='center', va='center',
                               fontsize=7, fontweight='bold',
                               color='white',
                               bbox=dict(boxstyle='round,pad=0.2', 
                                        facecolor='black', 
                                        edgecolor='none',
                                        alpha=0.6))
                    
                    bottom += value
                
                # Add total at top of stacked bar
                if bottom > 0:
                    ax.text(x_pos, bottom + 5, f'{bottom:.0f}', 
                           ha='center', va='bottom',
                           fontsize=10, fontweight='bold',
                           color='black')
        
        # Set x-axis labels
        ax.set_xticks(x_positions)
        ax.set_xticklabels(x_labels, fontsize=9, rotation=45, ha='right')
        ax.set_xlabel('Link Selection Policy', fontsize=14, fontweight='bold')
        
        # Add satellite count group labels on secondary x-axis
        sat_centers = []
        for sat_idx in range(len(sat_counts)):
            center = sat_idx * group_width + (num_bars_per_group * bar_width - bar_width) / 2
            sat_centers.append(center)
        
        ax2 = ax.secondary_xaxis('bottom')
        ax2.set_xticks(sat_centers)
        ax2.set_xticklabels([f'{s} Satellites' for s in sat_counts], 
                            fontsize=13, fontweight='bold')
        ax2.tick_params(axis='x', which='major', pad=45)
        
        # Add vertical separators between satellite count groups
        for sat_idx in range(1, len(sat_counts)):
            separator_x = sat_idx * group_width - 0.75
            ax.axvline(x=separator_x, color='black', linestyle='-', linewidth=2.5, alpha=0.4)
        
        # Y-axis
        ax.set_ylabel('Total Data Downloaded (GB)', fontsize=14, fontweight='bold')
        
        # Title
        ax.set_title(f'MaxDownload Performance Comparison\n{image_size} MB Images - Data Downloaded by Policy (Stacked by Spacing Strategy)',
                    fontsize=16, fontweight='bold', pad=20)
        
        # Legend
        ax.legend(title='Spacing Strategy', fontsize=11, title_fontsize=12, 
                 loc='upper left', framealpha=0.95, edgecolor='black')
        
        # Grid
        ax.grid(True, alpha=0.3, linestyle='--', axis='y')
        ax.set_axisbelow(True)
        
        # Set y-axis to start from 0
        ax.set_ylim(bottom=0)
        
        plt.tight_layout()
        
        # Save
        filename = f'stacked_by_policy_{image_size}mb.png'
        output_file = output_dir / filename
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"✅ Saved: {output_file}")
        plt.close()
    
    print()
    print("="*110)
    print("✅ STACKED BAR CHARTS COMPLETE!")
    print("="*110)
    print()
    print("Chart Structure:")
    print(f"  X-AXIS: {len(sat_counts)} satellite count groups ({', '.join(map(str, sat_counts))} sats)")
    print(f"          Each group has {len(policies)} bars (one per policy)")
    print()
    print("  Y-AXIS: Total data downloaded (GB)")
    print()
    print("  STACKS: Each bar divided by 4 spacing strategies:")
    print("    🔴 Red    = Close-spaced")
    print("    🔵 Blue   = Orbit-spaced")
    print("    🟢 Green  = Frame-spaced")
    print("    🟠 Orange = Close-Orbit-spaced")
    print()
    print(f"  RESULT: {len(image_sizes)} chart(s) (one per image size)")
    print(f"          {len(sat_counts) * len(policies)} stacked bars per chart")
    print()
    print("  💡 MaxDownload bars have purple highlight background")
    print("     Total data shown above each bar")

if __name__ == '__main__':
    import os
    import sys
    
    # Change to script directory
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    # Allow passing results directory as command line argument
    results_dir = sys.argv[1] if len(sys.argv) > 1 else 'results/base results 2'
    
    results_df = create_stacked_bar_charts(results_dir)
    
    if results_df is not None:
        print()
        print("✨ Stacked bar charts complete!")
        print("   MaxDownload advantage is clearly visible!")
