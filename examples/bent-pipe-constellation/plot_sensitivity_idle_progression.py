#!/usr/bin/env python3
"""
Create sensitivity study idle time progression charts for orbit-spaced only.

Shows percentage idle time across constellation sizes: 1, 10, 15, 17, 18, 19, 20, 25, 50, 100, 200

Creates 6 charts (one per image size), each with 2 panels:
- Left: Total Idle Time % (system-level waste)
- Right: Connected Idle Time % (link-level waste)

Each panel has 4 lines (one per policy):
- Red solid (sticky), Blue dashed (fifo), Green dotted (roundrobin), Orange dash-dot (random)
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import zipfile
from pathlib import Path
import re

# Configuration - use absolute paths
SCRIPT_DIR = Path(__file__).parent.absolute()

def scan_sensitivity_configurations(search_dirs):
    """Scan sensitivity study directories for orbit-spaced configurations"""
    configs = []
    
    for search_dir in search_dirs:
        search_path = SCRIPT_DIR / search_dir if not Path(search_dir).is_absolute() else Path(search_dir)
        
        if not search_path.exists():
            print(f"⚠️  Warning: {search_path} does not exist")
            continue
            
        for folder in search_path.glob('constellation_analysis_*'):
            if not folder.is_dir():
                continue
            
            # Parse folder name: constellation_analysis_YYYYMMDD_HHMMSS_IMAGESIZE_NUMSATS
            match = re.match(r'constellation_analysis_\d{8}_\d{6}_(\d+)_(\d+)', folder.name)
            if match:
                image_size_kb = int(match.group(1))
                num_sats = int(match.group(2))
                
                # Only orbit-spaced strategy
                strategy_path = folder / 'orbit-spaced' / 'simulation_logs.zip'
                if strategy_path.exists():
                    configs.append({
                        'folder': folder,
                        'strategy': 'orbit-spaced',
                        'image_size_kb': image_size_kb,
                        'num_sats': num_sats,
                        'zip_path': strategy_path
                    })
    
    return pd.DataFrame(configs)

def get_idle_metrics(zip_path, policy='fifo'):
    """
    Get idle time metrics from visibility log.
    
    Returns percentage idle time:
    - Total idle % = (simulation_time - productive_time) / simulation_time * 100
    - Connected idle % = (connected_but_empty) / total_connected * 100
    """
    try:
        with zipfile.ZipFile(zip_path, 'r') as zipf:
            with zipf.open(f'{policy}/visibility_log.csv') as f:
                df = pd.read_csv(f)
        
        if len(df) == 0:
            return None
        
        # Get simulation duration (6 hours = 21600 seconds)
        sim_duration = 21600
        
        # TOTAL IDLE CALCULATION:
        # Productive = connected=1 AND buffer_mb > 0.001
        # Total idle time = simulation_duration - productive_time
        
        productive_events = df[(df['connected'] == 1) & (df['buffer_mb'] > 0.001)]
        actual_productive_time = len(productive_events)  # Each event = 1 second
        
        total_idle_time = sim_duration - actual_productive_time
        total_idle_pct = (total_idle_time / sim_duration) * 100
        
        # CONNECTED IDLE CALCULATION:
        # Connected idle: connected but buffer empty (connected=1 AND buffer <= 0.001 MB)
        connected_idle_events = len(df[(df['connected'] == 1) & (df['buffer_mb'] <= 0.001)])
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
        print(f"  ⚠️  Error reading {zip_path}/{policy}: {e}")
        return None

def create_sensitivity_charts():
    """Create sensitivity study progression charts for orbit-spaced only"""
    
    print("="*110)
    print("=" * 30 + " SENSITIVITY STUDY - IDLE TIME PROGRESSION")
    print("Orbit-Spaced Only, All Policies")
    print("="*110)
    print()
    
    # Search in both sensitivity and base results directories
    search_dirs = [
        'results/orbit space best constellation size',
        'results/orbit space sensitivity 2',
        'results/base results 2'
    ]
    
    print("Scanning for orbit-spaced configurations in sensitivity study...")
    configs_df = scan_sensitivity_configurations(search_dirs)
    
    if len(configs_df) == 0:
        print("❌ No configurations found!")
        return
    
    print(f"Found {len(configs_df)} orbit-spaced configurations")
    print()
    
    # Collect all data
    results = []
    policies = ['sticky', 'fifo', 'roundrobin', 'random']
    
    for _, config in configs_df.iterrows():
        image_size_mb = config['image_size_kb'] / 1000.0
        
        for policy in policies:
            metrics = get_idle_metrics(config['zip_path'], policy)
            
            if metrics is not None:
                results.append({
                    'image_size_mb': image_size_mb,
                    'image_size_kb': config['image_size_kb'],
                    'strategy': 'orbit-spaced',
                    'policy': policy,
                    'num_sats': config['num_sats'],
                    **metrics
                })
    
    results_df = pd.DataFrame(results)
    
    if len(results_df) == 0:
        print("❌ No valid data collected!")
        return
    
    # Deduplicate: Keep only one entry per (image_size_kb, num_sats, policy) combination
    # This handles cases where the same constellation size appears in multiple source directories
    print(f"Collected {len(results_df)} total entries")
    results_df = results_df.drop_duplicates(subset=['image_size_kb', 'num_sats', 'policy'], keep='first')
    print(f"After deduplication: {len(results_df)} unique entries")
    print()
    
    # Save raw data
    output_dir = SCRIPT_DIR / "constellation_analysis" / "sensitivity_idle_progression"
    output_dir.mkdir(parents=True, exist_ok=True)
    results_df.to_csv(output_dir / 'sensitivity_idle_progression.csv', index=False)
    print(f"✅ Saved: {output_dir / 'sensitivity_idle_progression.csv'}")
    print()
    
    # Create charts
    create_charts(results_df, output_dir)
    
    return results_df

def create_charts(results_df, output_dir):
    """Create one 2-panel chart per image size"""
    
    # Get unique values
    image_sizes = sorted(results_df['image_size_mb'].unique())
    policies = ['sticky', 'fifo', 'roundrobin', 'random']
    
    # Define constellation sizes we want to plot (in order)
    target_sat_counts = [1, 10, 15, 17, 18, 19, 20, 25, 50, 100, 200]
    
    # Policy colors and styles
    policy_colors = {
        'sticky': '#E63946',      # Red
        'fifo': '#2E86AB',        # Blue
        'roundrobin': '#06A77D',  # Green
        'random': '#F77F00'       # Orange
    }
    
    policy_styles = {
        'sticky': '-',        # Solid
        'fifo': '--',         # Dashed
        'roundrobin': ':',    # Dotted
        'random': '-.'        # Dash-dot
    }
    
    policy_markers = {
        'sticky': 'o',        # Circle
        'fifo': 's',          # Square
        'roundrobin': '^',    # Triangle
        'random': 'D'         # Diamond
    }
    
    print(f"Creating charts for {len(image_sizes)} image size(s)...")
    print()
    
    for image_size in image_sizes:
        # Filter for this image size
        df_img = results_df[results_df['image_size_mb'] == image_size].copy()
        
        if len(df_img) == 0:
            continue
        
        # Get available constellation sizes for this image (filter to target sizes)
        available_sats = sorted(df_img['num_sats'].unique())
        sat_counts = [s for s in target_sat_counts if s in available_sats]
        
        if len(sat_counts) < 2:
            print(f"⚠️  Skipping {image_size:.3f} MB - insufficient data points")
            continue
        
        print(f"Creating chart for {image_size:.3f} MB ({len(sat_counts)} constellation sizes)...")
        
        # Create figure with 2 panels side-by-side
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 7))
        fig.suptitle(f'Idle Time Progression - Orbit-Spaced - {image_size:.3f} MB Images', 
                     fontsize=16, fontweight='bold', y=0.98)
        
        # Plot each policy
        for policy in policies:
            df_policy = df_img[df_img['policy'] == policy].copy()
            
            # Filter to available constellation sizes and sort
            df_policy = df_policy[df_policy['num_sats'].isin(sat_counts)].sort_values('num_sats')
            
            if len(df_policy) == 0:
                continue
            
            color = policy_colors[policy]
            style = policy_styles[policy]
            marker = policy_markers[policy]
            
            # Left panel: Total Idle %
            ax1.plot(df_policy['num_sats'], df_policy['total_idle_pct'],
                    color=color, linestyle=style, marker=marker, markersize=8,
                    linewidth=2.5, label=policy.upper(), alpha=0.8)
            
            # Right panel: Connected Idle %
            ax2.plot(df_policy['num_sats'], df_policy['connected_idle_pct'],
                    color=color, linestyle=style, marker=marker, markersize=8,
                    linewidth=2.5, label=policy.upper(), alpha=0.8)
        
        # Configure left panel (Total Idle %)
        ax1.set_xlabel('Number of Satellites', fontsize=12, fontweight='bold')
        ax1.set_ylabel('Total Idle Time (%)', fontsize=12, fontweight='bold')
        ax1.set_title('Total Idle Time %\n(System-Level Waste)', fontsize=13, fontweight='bold', pad=15)
        ax1.grid(True, alpha=0.3, linestyle='--')
        ax1.legend(loc='upper right', framealpha=0.95, fontsize=11)
        ax1.set_xticks(sat_counts)
        ax1.set_xticklabels([str(s) for s in sat_counts], rotation=45)
        
        # Configure right panel (Connected Idle %)
        ax2.set_xlabel('Number of Satellites', fontsize=12, fontweight='bold')
        ax2.set_ylabel('Connected Idle Time (%)', fontsize=12, fontweight='bold')
        ax2.set_title('Connected Idle Time %\n(Link-Level Waste)', fontsize=13, fontweight='bold', pad=15)
        ax2.grid(True, alpha=0.3, linestyle='--')
        ax2.legend(loc='upper right', framealpha=0.95, fontsize=11)
        ax2.set_xticks(sat_counts)
        ax2.set_xticklabels([str(s) for s in sat_counts], rotation=45)
        
        # Add info box
        info_text = (
            f"Strategy: Orbit-Spaced\n"
            f"Image Size: {image_size:.3f} MB\n"
            f"Constellation Sizes: {len(sat_counts)}\n"
            f"Policies: {len(policies)}"
        )
        fig.text(0.02, 0.02, info_text, fontsize=10, verticalalignment='bottom',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.3))
        
        plt.tight_layout(rect=[0, 0.03, 1, 0.96])
        
        # Save chart
        filename = f'sensitivity_idle_progression_{image_size:.3f}mb.png'
        filepath = output_dir / filename
        plt.savefig(filepath, dpi=150, bbox_inches='tight')
        plt.close()
        
        print(f"✅ Saved: {filepath}")
    
    print()
    print("="*110)
    print("✅ SENSITIVITY IDLE PROGRESSION CHARTS COMPLETE!")
    print("="*110)
    print()
    print("Chart Structure:")
    print("  LEFT PANEL: Total Idle Time %")
    print("    - Definition: (simulation_time - productive_time) / simulation_time * 100")
    print("    - Shows: Overall system efficiency")
    print()
    print("  RIGHT PANEL: Connected Idle Time %")
    print("    - Definition: (connected_but_empty) / total_connected * 100")
    print("    - Shows: Link utilization efficiency")
    print()
    print("  LINES: 4 policies per panel")
    print("    🔴 Red solid     = STICKY")
    print("    🔵 Blue dashed   = FIFO")
    print("    🟢 Green dotted  = ROUNDROBIN")
    print("    🟠 Orange dashdot = RANDOM")
    print()
    print(f"  CONSTELLATION SIZES: {len(target_sat_counts)} ({', '.join(map(str, target_sat_counts))})")
    print()
    print("✨ Charts complete!")

if __name__ == '__main__':
    create_sensitivity_charts()
