#!/usr/bin/env python3
"""
Generate optimized data download clustered bar chart for 2.8 MB images
Based on professor feedback:
- Shorter and wider figure
- 5x larger fonts
- Satellite count color-coded legend
- Remove redundant "spaced" words
- Add data download values on top of bars
"""

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import zipfile
from pathlib import Path
import numpy as np

# Configuration
BASE_DIR = Path('/Users/chrischeshire/github/cote-constellation/examples/bent-pipe-constellation')
OUTPUT_DIR = BASE_DIR / 'design_comparison' / 'datadown_analysis'
FOCUS_IMAGE_SIZE = 2.799  # MB

def scan_configurations():
    """Scan for 2.8 MB configurations"""
    configs = []
    
    # Scan main directory
    for parent_folder in BASE_DIR.glob('constellation_analysis_*'):
        parts = parent_folder.name.split('_')
        if len(parts) >= 5:
            image_size_kb = int(parts[4])
            sat_count = int(parts[5])
            image_size = image_size_kb / 1000.0
            
            if abs(image_size - FOCUS_IMAGE_SIZE) < 0.01:
                for strategy_folder in parent_folder.iterdir():
                    if strategy_folder.is_dir() and 'spaced' in strategy_folder.name:
                        configs.append({
                            'folder': strategy_folder,
                            'strategy': strategy_folder.name,
                            'sat_count': sat_count,
                            'image_size': image_size
                        })
    
    # Scan results directory for additional data (e.g., 15-satellite runs)
    results_dir = BASE_DIR / 'results' / 'maxdownload_20251125_081912'
    if results_dir.exists():
        for parent_folder in results_dir.glob('constellation_analysis_*'):
            parts = parent_folder.name.split('_')
            if len(parts) >= 5:
                image_size_kb = int(parts[4])
                sat_count = int(parts[5])
                image_size = image_size_kb / 1000.0
                
                if abs(image_size - FOCUS_IMAGE_SIZE) < 0.01:
                    for strategy_folder in parent_folder.iterdir():
                        if strategy_folder.is_dir() and 'spaced' in strategy_folder.name:
                            configs.append({
                                'folder': strategy_folder,
                                'strategy': strategy_folder.name,
                                'sat_count': sat_count,
                                'image_size': image_size
                            })
    
    # Also scan for 15-satellite data in newer results directory
    results_dir_new = BASE_DIR / 'results' / 'maxdownload_20260104_141314'
    if results_dir_new.exists():
        for parent_folder in results_dir_new.glob('constellation_analysis_*'):
            parts = parent_folder.name.split('_')
            if len(parts) >= 5:
                image_size_kb = int(parts[4])
                sat_count = int(parts[5])
                image_size = image_size_kb / 1000.0
                
                if abs(image_size - FOCUS_IMAGE_SIZE) < 0.01:
                    for strategy_folder in parent_folder.iterdir():
                        if strategy_folder.is_dir() and 'spaced' in strategy_folder.name:
                            configs.append({
                                'folder': strategy_folder,
                                'strategy': strategy_folder.name,
                                'sat_count': sat_count,
                                'image_size': image_size
                            })
    
    return configs

def extract_data_download(config, policy):
    """Extract total data downloaded in GB"""
    zip_path = config['folder'] / 'simulation_logs.zip'
    
    if not zip_path.exists():
        return None
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            log_file = f'{policy}/visibility_log.csv'
            if log_file not in z.namelist():
                return None
            
            with z.open(log_file) as f:
                df = pd.read_csv(f)
                
                # Calculate total data downloaded in GB
                total_downloaded_mb = df['downloaded_mb'].sum()
                total_downloaded_gb = total_downloaded_mb / 1000.0
                
                return total_downloaded_gb
    except Exception as e:
        return None

def create_optimized_clustered_bar_chart(df):
    """
    Create optimized 2x2 grid with professor's specifications:
    - Shorter and wider
    - 5x larger fonts
    - Color-coded legend for satellite counts
    - Remove "spaced" redundancy
    - Values on top of bars
    """
    
    fig, axes = plt.subplots(2, 2, figsize=(28, 10))  # Wider and shorter
    axes = axes.flatten()
    
    strategies_ordered = ['close-spaced', 'frame-spaced', 'orbit-spaced', 'close-orbit-spaced']
    # Remove "Spaced" and "-Spaced" from labels
    strategy_labels = ['Close', 'Frame', 'Orbit', 'Close-Orbit']
    
    policies = ['fifo', 'sticky', 'roundrobin', 'random']
    policy_labels = {
        'fifo': 'FIFO',
        'sticky': 'Sticky',
        'roundrobin': 'Round Robin',
        'random': 'Random'
    }
    
    sat_counts = sorted(df['sat_count'].unique())
    colors = plt.cm.viridis(np.linspace(0.2, 0.9, len(sat_counts)))
    
    for idx, policy in enumerate(policies):
        ax = axes[idx]
        
        policy_data = df[df['policy'] == policy]
        
        n_strategies = len(strategies_ordered)
        n_sat_counts = len(sat_counts)
        
        x = np.arange(n_strategies)
        width = 0.15
        
        for i, sat_count in enumerate(sat_counts):
            datadowns = []
            
            for j, strategy in enumerate(strategies_ordered):
                subset = policy_data[(policy_data['strategy'] == strategy) & 
                                    (policy_data['sat_count'] == sat_count)]
                if len(subset) > 0:
                    dd_val = subset['data_download_gb'].values[0]
                    datadowns.append(dd_val)
                else:
                    dd_val = 0
                    datadowns.append(0)
            
            offset = width * (i - (n_sat_counts - 1) / 2)
            bars = ax.bar(x + offset, datadowns, width,
                         label=f'{sat_count} Satellites',
                         color=colors[i],
                         edgecolor='black', linewidth=2, alpha=0.9)
            
            # Add data download values on top of bars
            for bar, dd_val in zip(bars, datadowns):
                height = bar.get_height()
                if height > 0:
                    ax.text(bar.get_x() + bar.get_width()/2., height + 5,
                           f'{dd_val:.0f}',
                           ha='center', va='bottom', fontsize=20, fontweight='bold')
        
        # Formatting
        ax.set_ylabel('Data Downloaded (GB)', fontsize=28, fontweight='bold')
        ax.set_title(f'{policy_labels[policy]}', fontsize=30, fontweight='bold', pad=20)
        ax.set_xticks(x)
        ax.set_xticklabels(strategy_labels, fontsize=20, fontweight='bold')
        
        # Set y-axis limits based on data
        max_val = policy_data['data_download_gb'].max()
        ax.set_ylim(0, max_val * 1.15)
        
        ax.grid(True, alpha=0.2, linestyle='-', linewidth=1.5, axis='y', zorder=1)
        ax.set_axisbelow(True)
        
        # Add legend with satellite counts
        ax.legend(loc='upper left', fontsize=16, frameon=True, fancybox=False,
                 edgecolor='black', framealpha=0.95, ncol=1)
        
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_linewidth(3)
        ax.spines['bottom'].set_linewidth(3)
        
        # Adjust tick parameters
        ax.tick_params(axis='both', which='major', width=3, length=10)
        ax.tick_params(axis='y', labelsize=24)
    
    plt.tight_layout()
    return fig

def main():
    print("="*70)
    print("OPTIMIZED DATA DOWNLOAD PLOT: 2.8 MB Images")
    print("="*70)
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print(f"\n🔍 Scanning configurations...")
    configs = scan_configurations()
    print(f"✅ Found {len(configs)} configurations")
    
    print("\n📊 Collecting data...")
    policies = ['fifo', 'sticky', 'roundrobin', 'random']
    all_data = []
    
    for config in configs:
        for policy in policies:
            data_download = extract_data_download(config, policy)
            if data_download is not None:
                all_data.append({
                    'strategy': config['strategy'],
                    'policy': policy,
                    'sat_count': config['sat_count'],
                    'data_download_gb': data_download
                })
    
    df = pd.DataFrame(all_data)
    print(f"✅ Collected {len(df)} data points")
    
    print("\n🎨 Generating optimized plot...")
    fig = create_optimized_clustered_bar_chart(df)
    
    output_path = OUTPUT_DIR / 'datadown_clustered_optimized.png'
    fig.savefig(output_path, dpi=300, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    
    print("\n" + "="*70)
    print("✅ COMPLETE!")
    print("="*70)
    print(f"\n📊 Saved: {output_path}")
    
    print("\n📈 Key Features:")
    print("   ✓ Shorter and wider layout (28x10)")
    print("   ✓ 5x larger fonts")
    print("   ✓ Color-coded satellite count legend")
    print("   ✓ Removed 'Spaced' redundancy from labels")
    print("   ✓ Data download values displayed on top of bars")
    print("   ✓ Clean, publication-ready appearance")

if __name__ == '__main__':
    main()
