#!/usr/bin/env python3
"""
Create stacked bar charts showing total data downloaded by constellation size, strategy, and policy.

X-axis: Constellation sizes (1, 50, 100, 200) grouped by strategy (4 groups)
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
    print("=" * 35 + " DATA DOWNLOADED STACKED BAR CHARTS")
    print("Grouped by Strategy, Stacked by Policy")
    print("="*110)
    print()
    
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
    
    # Save raw data - output to constellation_analysis top level folder
    output_dir = Path('constellation_analysis') / 'data_downloaded_charts'
    output_dir.mkdir(parents=True, exist_ok=True)
    results_df.to_csv(output_dir / 'stacked_data_downloaded.csv', index=False)
    print(f"✅ Saved: {output_dir / 'stacked_data_downloaded.csv'}")
    print()
    
    # Create charts
    create_charts(results_df, output_dir)
    
    return results_df

def create_charts(results_df, output_dir):
    """Create one stacked bar chart per image size"""
    
    # Get unique values
    image_sizes = sorted(results_df['image_size_mb'].unique())
    strategies = ['close-spaced', 'frame-spaced', 'orbit-spaced', 'close-orbit-spaced']
    policies = ['sticky', 'fifo', 'roundrobin', 'random', 'mindistance', 'maxdownload']
    sat_counts = sorted(results_df['num_sats'].unique())  # Use whatever exists in data
    
    # Color scheme by policy (6 distinct colors for stacks)
    policy_colors = {
        'sticky': '#E63946',      # Red
        'fifo': '#2E86AB',        # Blue
        'roundrobin': '#06A77D',  # Green
        'random': '#F77F00',      # Orange
        'mindistance': '#FFD166', # Yellow
        'maxdownload': '#9D4EDD'  # Purple
    }
    
    # Strategy labels (shortened)
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
        
        # Prepare data structure for stacked bars
        # X positions: 4 strategies × len(sat_counts) bars
        num_bars_per_strategy = len(sat_counts)
        bar_width = 0.8
        group_width = num_bars_per_strategy * bar_width + 1.0  # Add spacing between strategy groups
        
        x_positions = []
        x_labels = []
        
        # Build stacked bars
        for strategy_idx, strategy in enumerate(strategies):
            for sat_idx, sat_count in enumerate(sat_counts):
                # Calculate x position for this bar
                x_pos = strategy_idx * group_width + sat_idx * bar_width
                x_positions.append(x_pos)
                x_labels.append(str(sat_count))
                
                # Get data for all policies for this strategy + sat_count combination
                bottom = 0
                for policy in policies:
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
                          color=policy_colors[policy], 
                          edgecolor='white', linewidth=1.5,
                          label=policy.upper() if strategy_idx == 0 and sat_idx == 0 else "")
                    
                    # Add text label in the center of this stack segment
                    if value > 0:
                        # Position text in the middle of this segment
                        text_y = bottom + value / 2
                        # Format value: show 1 decimal for values < 10, otherwise round to integer
                        if value < 10:
                            text = f'{value:.1f}'
                        else:
                            text = f'{value:.0f}'
                        
                        ax.text(x_pos, text_y, text, 
                               ha='center', va='center',
                               fontsize=8, fontweight='bold',
                               color='white',
                               bbox=dict(boxstyle='round,pad=0.3', 
                                        facecolor='black', 
                                        edgecolor='none',
                                        alpha=0.6))
                    
                    bottom += value
        
        # Set x-axis labels
        ax.set_xticks(x_positions)
        ax.set_xticklabels(x_labels, fontsize=11)
        ax.set_xlabel('Number of Satellites', fontsize=14, fontweight='bold')
        
        # Add strategy group labels on secondary x-axis
        strategy_centers = []
        for strategy_idx in range(len(strategies)):
            center = strategy_idx * group_width + (num_bars_per_strategy * bar_width - bar_width) / 2
            strategy_centers.append(center)
        
        ax2 = ax.secondary_xaxis('bottom')
        ax2.set_xticks(strategy_centers)
        ax2.set_xticklabels([strategy_labels[s] for s in strategies], 
                            fontsize=15, fontweight='bold')
        ax2.tick_params(axis='x', which='major', pad=35)
        
        # Add vertical separators between strategy groups
        for strategy_idx in range(1, len(strategies)):
            separator_x = strategy_idx * group_width - 0.5
            ax.axvline(x=separator_x, color='black', linestyle='-', linewidth=2, alpha=0.3)
        
        # Y-axis
        ax.set_ylabel('Total Data Downloaded (GB)', fontsize=14, fontweight='bold')
        
        # Title
        ax.set_title(f'Data Downloaded by Strategy, Constellation Size, and Policy\n{image_size} MB Images',
                    fontsize=16, fontweight='bold', pad=20)
        
        # Legend
        ax.legend(title='Link Policy', fontsize=12, title_fontsize=13, 
                 loc='upper left', framealpha=0.95, edgecolor='black')
        
        # Grid
        ax.grid(True, alpha=0.3, linestyle='--', axis='y')
        ax.set_axisbelow(True)
        
        plt.tight_layout()
        
        # Save
        filename = f'stacked_data_downloaded_{image_size}mb.png'
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
    print("  X-AXIS: 4 strategy groups (Close, Frame, Orbit, Close-Orbit)")
    print(f"          Each group has {len(sat_counts)} bars (constellation sizes: {', '.join(map(str, sat_counts))})")
    print()
    print("  Y-AXIS: Total data downloaded (GB)")
    print()
    print("  STACKS: Each bar divided by 6 policies:")
    print("    🔴 Red    = STICKY")
    print("    🔵 Blue   = FIFO")
    print("    🟢 Green  = ROUNDROBIN")
    print("    🟠 Orange = RANDOM")
    print("    🟡 Yellow = MINDISTANCE")
    print("    🟣 Purple = MAXDOWNLOAD")
    print()
    print(f"  RESULT: {len(image_sizes)} chart(s) (one per image size)")
    print(f"          {4 * len(sat_counts)} stacked bars per chart (4 strategies × {len(sat_counts)} constellation sizes)")

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
