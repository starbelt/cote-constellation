#!/usr/bin/env python3
"""
Create combined idle time progression charts.

Instead of 12 separate charts (4 image sizes × 3 strategies),
create 4 mega-charts (one per image size) with all strategies and policies combined.

Each chart has 2 panels (side-by-side):
- Left: Total Idle Time (system-level waste)
- Right: Connected Idle Time (link-level waste)

Each panel has 16 lines:
- 4 strategies (close, orbit, frame, close-orbit) × 4 policies (sticky, fifo, roundrobin, random)
- Colors: Red (close), Blue (orbit), Green (frame), Orange (close-orbit)
- Line styles: Solid (sticky), Dashed (fifo), Dotted (roundrobin), Dash-dot (random)
- Markers: Circle (sticky), Square (fifo), Triangle (roundrobin), Diamond (random)
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import zipfile
from pathlib import Path
import re

def scan_all_configurations(search_dir='.'):
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

def get_idle_metrics(zip_path, policy='fifo'):
    """Get idle time metrics from visibility log"""
    try:
        with zipfile.ZipFile(zip_path, 'r') as zipf:
            with zipf.open(f'{policy}/visibility_log.csv') as f:
                df = pd.read_csv(f)
        
        if len(df) == 0:
            return None
        
        # Get simulation duration (6 hours = 21600 seconds)
        sim_duration = 21600
        
        # TOTAL IDLE CALCULATION (matches 4D matrix logic):
        # Total idle = time when system is NOT productively active
        # Productive = connected=1 AND buffer_mb > 0.001
        # Total idle time = simulation_duration - productive_time
        
        # Count productive events: connected AND buffer has data
        productive_events = df[(df['connected'] == 1) & (df['buffer_mb'] > 0.001)]
        actual_productive_time = len(productive_events)  # Each event = 1 second
        
        # Total idle time = simulation duration - productive time
        total_idle_time = sim_duration - actual_productive_time
        total_idle_pct = (total_idle_time / sim_duration) * 100
        
        # CONNECTED IDLE CALCULATION:
        # Connected idle: connected but buffer empty (connected=1 AND buffer <= 0.001 MB)
        connected_idle_events = len(df[(df['connected'] == 1) & (df['buffer_mb'] <= 0.001)])
        
        # Total connected events (for percentage calculation)
        total_connected_events = len(df[df['connected'] == 1])
        
        if total_connected_events > 0:
            connected_idle_pct = (connected_idle_events / total_connected_events) * 100
        else:
            connected_idle_pct = 0
        
        return {
            'sim_duration': sim_duration,
            'productive_time': actual_productive_time,
            'total_idle_time': total_idle_time,
            'total_idle_pct': total_idle_pct,
            'total_connected_events': total_connected_events,
            'connected_idle_events': connected_idle_events,
            'connected_idle_pct': connected_idle_pct
        }
    except Exception as e:
        print(f"  ⚠️  Error reading {zip_path}: {e}")
        return None

def create_combined_charts():
    """Create combined charts - one per image size with all strategies and policies"""
    
    print("="*110)
    print("=" * 42 + " COMBINED IDLE TIME PROGRESSION")
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
            metrics = get_idle_metrics(row['zip_path'], policy)
            
            if metrics is not None:
                results.append({
                    'image_size_mb': image_size_mb,
                    'strategy': strategy,
                    'policy': policy,
                    'num_sats': num_sats,
                    **metrics
                })
    
    results_df = pd.DataFrame(results)
    
    # Save raw data
    output_dir = Path('comparison_charts')
    output_dir.mkdir(exist_ok=True)
    results_df.to_csv(output_dir / 'combined_idle_analysis.csv', index=False)
    print(f"✅ Saved: {output_dir / 'combined_idle_analysis.csv'}")
    print()
    
    # Create charts
    create_charts(results_df, output_dir)
    
    return results_df

def create_charts(results_df, output_dir):
    """Create one 2-panel chart per image size with all strategies and policies"""
    
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
    
    # Create one 2-panel chart per image size
    for image_size in image_sizes:
        print(f"Creating combined chart for {image_size} MB...")
        
        subset = results_df[results_df['image_size_mb'] == image_size]
        
        if len(subset) == 0:
            continue
        
        # Create 2-panel figure
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(24, 10))
        
        # Plot all 16 combinations on BOTH panels
        for strategy in strategies:
            for policy in policies:
                data = subset[(subset['strategy'] == strategy) & (subset['policy'] == policy)]
                
                if len(data) == 0:
                    continue
                
                # Sort by satellite count
                data = data.sort_values('num_sats')
                
                x_vals = data['num_sats'].values
                total_idle_vals = data['total_idle_pct'].values
                connected_idle_vals = data['connected_idle_pct'].values
                
                if len(x_vals) > 0:
                    # Create label
                    strategy_short = strategy.replace('-spaced', '').replace('-', ' ').title()
                    label = f'{strategy_short} - {policy.upper()}'
                    
                    # PANEL 1: Total Idle Time
                    ax1.plot(x_vals, total_idle_vals, 
                            marker=policy_markers[policy], 
                            markersize=10,
                            linewidth=3,
                            linestyle=policy_styles[policy],
                            color=strategy_colors[strategy],
                            label=label,
                            alpha=0.9,
                            markeredgewidth=1.5,
                            markeredgecolor='white')
                    
                    # PANEL 2: Connected Idle Time
                    ax2.plot(x_vals, connected_idle_vals, 
                            marker=policy_markers[policy], 
                            markersize=10,
                            linewidth=3,
                            linestyle=policy_styles[policy],
                            color=strategy_colors[strategy],
                            label=label,
                            alpha=0.9,
                            markeredgewidth=1.5,
                            markeredgecolor='white')
        
        # PANEL 1: Total Idle Time
        ax1.set_xlabel('Number of Satellites', fontsize=14, fontweight='bold')
        ax1.set_ylabel('Total Idle Time - No Data to Send (%)', fontsize=14, fontweight='bold')
        ax1.set_title(f'Total Idle Time (Lower is Better)\n{image_size} MB Images',
                     fontsize=15, fontweight='bold')
        ax1.legend(fontsize=8, loc='best', ncol=2, framealpha=0.95, edgecolor='black', fancybox=True)
        ax1.grid(True, alpha=0.3, linestyle='--')
        ax1.set_ylim([0, 105])
        ax1.axhline(y=50, color='orange', linestyle='--', linewidth=2, alpha=0.5)
        ax1.axhline(y=90, color='red', linestyle='--', linewidth=2, alpha=0.5)
        
        # PANEL 2: Connected Idle Time
        ax2.set_xlabel('Number of Satellites', fontsize=14, fontweight='bold')
        ax2.set_ylabel('Connected Idle Time - Wasted Link Time (%)', fontsize=14, fontweight='bold')
        ax2.set_title(f'Connected Idle Time (Lower is Better)\n{image_size} MB Images',
                     fontsize=15, fontweight='bold')
        ax2.legend(fontsize=8, loc='best', ncol=2, framealpha=0.95, edgecolor='black', fancybox=True)
        ax2.grid(True, alpha=0.3, linestyle='--')
        ax2.set_ylim([0, 105])
        ax2.axhline(y=50, color='orange', linestyle='--', linewidth=2, alpha=0.5)
        ax2.axhline(y=90, color='red', linestyle='--', linewidth=2, alpha=0.5)
        
        # Set x-axis for both panels
        if len(sat_counts) > 0:
            ax1.set_xticks(sat_counts)
            ax1.set_xlim(min(sat_counts) - 10, max(sat_counts) + 10)
            ax2.set_xticks(sat_counts)
            ax2.set_xlim(min(sat_counts) - 10, max(sat_counts) + 10)
        
        plt.tight_layout()
        
        # Save
        filename = f'combined_idle_{image_size}mb.png'
        output_file = output_dir / filename
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"✅ Saved: {output_file}")
        plt.close()
    
    print()
    print("="*110)
    print("✅ COMBINED IDLE TIME CHARTS COMPLETE!")
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
    print("  RESULT: 16 lines per panel (4 strategies × 4 policies)")
    print("          4 total charts (one per image size)")
    print("          2 panels per chart (total idle + connected idle)")

if __name__ == '__main__':
    import os
    
    # Change to script directory
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    results_df = create_combined_charts()
    
    if results_df is not None:
        print()
        print("✨ Combined idle time charts complete!")
