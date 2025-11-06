#!/usr/bin/env python3
"""
Create combined data downloaded progression charts.

Instead of 12 separate charts (4 image sizes × 3 strategies),
create 4 mega-charts (one per image size) with all strategies and policies combined.

Each chart has 12 lines:
- 3 strategies (close, orbit, frame) × 4 policies (sticky, fifo, roundrobin, random)
- Colors: Red (close), Blue (orbit), Green (frame)
- Line styles: Solid (sticky), Dashed (fifo), Dotted (roundrobin), Dash-dot (random)
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import zipfile
from pathlib import Path
import re

# Configuration - use absolute paths
SCRIPT_DIR = Path(__file__).parent.absolute()

def scan_all_configurations(search_dir='results/base results 2'):
    """Scan for all constellation_analysis folders"""
    configs = []
    
    search_path = SCRIPT_DIR / search_dir if not Path(search_dir).is_absolute() else Path(search_dir)
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

def get_total_downloaded(zip_path, policy='fifo'):
    """Get total downloaded MB for a configuration"""
    try:
        with zipfile.ZipFile(zip_path, 'r') as zipf:
            with zipf.open(f'{policy}/visibility_log.csv') as f:
                df = pd.read_csv(f)
        
        # Sum all downloaded_mb where connected == 1
        total = df[df['connected'] == 1]['downloaded_mb'].sum()
        return total
    except Exception as e:
        print(f"  ⚠️  Error reading {zip_path}: {e}")
        return None

def create_combined_charts():
    """Create combined charts - one per image size with all strategies and policies"""
    
    print("="*110)
    print("=" * 38 + " COMBINED DATA DOWNLOADED PROGRESSION")
    print("All strategies and policies on one chart per image size")
    print("="*110)
    print()
    
    print("Scanning for constellation configurations...")
    configs_df = scan_all_configurations()
    
    if len(configs_df) == 0:
        print("❌ No configurations found!")
        return
    
    print(f"Found {len(configs_df)} configurations")
    print()
    
    # Collect all data
    results = []
    
    # Group by image_size, strategy, and num_sats
    grouped = configs_df.groupby(['image_size_kb', 'strategy', 'num_sats'])
    
    policies = ['sticky', 'fifo', 'roundrobin', 'random']
    
    for (image_size_kb, strategy, num_sats), group in grouped:
        image_size_mb = image_size_kb / 1000.0
        
        for policy in policies:
            row = group.iloc[0]
            total_mb = get_total_downloaded(row['zip_path'], policy)
            
            if total_mb is not None:
                results.append({
                    'image_size_mb': image_size_mb,
                    'strategy': strategy,
                    'policy': policy,
                    'num_sats': num_sats,
                    'total_mb': total_mb
                })
    
    results_df = pd.DataFrame(results)
    
    # Save raw data in centralized constellation_analysis directory
    output_dir = SCRIPT_DIR / "constellation_analysis" / "data_downloaded_progression"
    output_dir.mkdir(parents=True, exist_ok=True)
    results_df.to_csv(output_dir / 'combined_data_downloaded_analysis.csv', index=False)
    print(f"✅ Saved: {output_dir / 'combined_data_downloaded_analysis.csv'}")
    print()
    
    # Create charts
    create_charts(results_df, output_dir)
    
    return results_df

def create_charts(results_df, output_dir):
    """Create one chart per image size with all strategies and policies"""
    
    # Get unique values
    image_sizes = sorted(results_df['image_size_mb'].unique())
    strategies = ['close-spaced', 'orbit-spaced', 'frame-spaced', 'close-orbit-spaced']
    policies = ['sticky', 'fifo', 'roundrobin', 'random']
    sat_counts = sorted(results_df['num_sats'].unique())
    
    # Color scheme by strategy (4 distinct colors)
    strategy_colors = {
        'close-spaced': '#E63946',        # Red
        'orbit-spaced': '#2E86AB',        # Blue
        'frame-spaced': '#06A77D',        # Green
        'close-orbit-spaced': '#F77F00'   # Orange
    }
    
    # Line style by policy
    policy_styles = {
        'sticky': '-',        # Solid
        'fifo': '--',         # Dashed
        'roundrobin': ':',    # Dotted
        'random': '-.'        # Dash-dot
    }
    
    # Marker style by policy (for better distinction)
    policy_markers = {
        'sticky': 'o',        # Circle
        'fifo': 's',          # Square
        'roundrobin': '^',    # Triangle up
        'random': 'D'         # Diamond
    }
    
    # Create one chart per image size
    for image_size in image_sizes:
        print(f"Creating combined chart for {image_size} MB...")
        
        subset = results_df[results_df['image_size_mb'] == image_size]
        
        if len(subset) == 0:
            continue
        
        fig, ax = plt.subplots(figsize=(16, 10))
        
        # Plot all 16 combinations (4 strategies × 4 policies)
        for strategy in strategies:
            for policy in policies:
                data = subset[(subset['strategy'] == strategy) & (subset['policy'] == policy)]
                
                if len(data) == 0:
                    continue
                
                # Sort by satellite count
                data = data.sort_values('num_sats')
                
                x_vals = data['num_sats'].values
                y_vals = data['total_mb'].values / 1000.0  # Convert to GB
                
                if len(x_vals) > 0:
                    # Create label
                    strategy_short = strategy.replace('-spaced', '').replace('-', ' ').title()  # "Close", "Orbit", "Frame", "Close Orbit"
                    label = f'{strategy_short} - {policy.upper()}'
                    
                    # Plot line with thicker lines and distinct markers
                    ax.plot(x_vals, y_vals, 
                           marker=policy_markers[policy], 
                           markersize=10,  # Larger markers
                           linewidth=3,     # Thicker lines
                           linestyle=policy_styles[policy],
                           color=strategy_colors[strategy],
                           label=label,
                           alpha=0.9,
                           markeredgewidth=1.5,
                           markeredgecolor='white')  # White edge for better visibility
        
        # Formatting
        ax.set_xlabel('Number of Satellites', fontsize=14, fontweight='bold')
        ax.set_ylabel('Total Data Downloaded (GB)', fontsize=14, fontweight='bold')
        ax.set_title(f'Combined Data Downloaded Progression - {image_size} MB Images\n'
                    f'All Strategies and Policies',
                    fontsize=16, fontweight='bold')
        
        # Legend with 2 columns for readability
        ax.legend(fontsize=9, loc='best', ncol=2, framealpha=0.95, 
                 edgecolor='black', fancybox=True)
        ax.grid(True, alpha=0.3, linestyle='--')
        
        # Set x-axis
        if len(sat_counts) > 0:
            ax.set_xticks(sat_counts)
            ax.set_xlim(min(sat_counts) - 10, max(sat_counts) + 10)
        
        # Add y-axis starting from 0
        ax.set_ylim(bottom=0)
        
        plt.tight_layout()
        
        # Save
        filename = f'combined_data_downloaded_{image_size}mb.png'
        output_file = output_dir / filename
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"✅ Saved: {output_file}")
        plt.close()
    
    print()
    print("="*110)
    print("✅ COMBINED CHARTS COMPLETE!")
    print("="*110)
    print()
    print("Chart Legend:")
    print("  COLORS (Strategy):")
    print("    🔴 Red    = Close-spaced")
    print("    🔵 Blue   = Orbit-spaced")
    print("    🟢 Green  = Frame-spaced")
    print("    🟠 Orange = Close-Orbit-spaced")
    print()
    print("  LINE STYLES (Policy):")
    print("    ━━━━  Solid    = STICKY")
    print("    ━ ━ ━  Dashed   = FIFO")
    print("    ┈┈┈┈  Dotted   = ROUNDROBIN")
    print("    ━·━·  Dash-dot = RANDOM")
    print()
    print("  MARKERS (Policy):")
    print("    ⚫ Circle   = STICKY")
    print("    ◼  Square   = FIFO")
    print("    ▲ Triangle = ROUNDROBIN")
    print("    ◆ Diamond  = RANDOM")
    print()
    print("  RESULT: 16 lines per chart (4 strategies × 4 policies)")
    print("          4 total charts (one per image size)")

if __name__ == '__main__':
    import os
    
    # Change to script directory
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    results_df = create_combined_charts()
    
    if results_df is not None:
        print()
        print("✨ Proof of concept complete!")
        print("   If this works well, we can apply the same approach to:")
        print("   - Combined contention progression")
        print("   - Combined idle time progression")
