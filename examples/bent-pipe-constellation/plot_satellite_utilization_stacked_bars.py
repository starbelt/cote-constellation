#!/usr/bin/env python3
"""
Plot Satellite Utilization as Stacked Bars: Active vs Starved satellites

Shows what percentage of constellation satellites are actively used vs 
sitting starved (never contacted). This reveals satellite-level contention 
and resource waste.

KEY INSIGHT:
------------
- Orbit-spaced: ~100% utilized (all satellites get used)
- Frame-spaced: ~70-100% utilized (most satellites get used)
- Close-spaced: ~5% utilized (95% of satellites STARVED!)

This shows massive waste in close-spaced where satellites exist but never connect.
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import zipfile
from pathlib import Path
from typing import Dict, List, Tuple, Set
import re

# Configuration
BASE_DIR = Path(".")
OUTPUT_DIR = BASE_DIR / "utilization_stacked_charts"

STRATEGIES_MAP = {
    "close-spaced": "Close",
    "frame-spaced": "Frame",
    "orbit-spaced": "Orbit",
    "close-orbit-spaced": "Close-Orbit"
}

IMAGE_SIZES = {
    27: "27 KB",
    279: "279 KB",
    2799: "2.7 MB",
    28000: "28 MB",
    280000: "280 MB",
    1024000: "1 GB"
}

CONSTELLATION_SIZES = [1, 25, 50, 100, 200]
POLICIES = ["sticky", "fifo", "roundrobin", "random"]

def scan_all_configurations(search_dir='results/base results 2'):
    """Scan for all constellation_analysis folders"""
    configs = []
    
    search_path = Path(search_dir)
    for constellation_folder in search_path.glob('constellation_analysis_*'):
        if not constellation_folder.is_dir():
            continue
            
        match = re.match(r'constellation_analysis_\d{8}_\d{6}_(\d+)_(\d+)', constellation_folder.name)
        if not match:
            continue
            
        image_size = int(match.group(1))
        num_sats = int(match.group(2))
        
        for strategy_folder in constellation_folder.iterdir():
            if not strategy_folder.is_dir():
                continue
            
            strategy_name = strategy_folder.name
            if strategy_name not in STRATEGIES_MAP:
                continue
            
            zip_path = strategy_folder / 'simulation_logs.zip'
            if not zip_path.exists():
                continue
            
            try:
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    policy_folders = set()
                    for filename in zip_ref.namelist():
                        parts = filename.split('/')
                        if len(parts) > 1 and parts[0] in POLICIES:
                            policy_folders.add(parts[0])
                    
                    for policy in policy_folders:
                        configs.append({
                            'strategy_folder': strategy_folder,
                            'image_size': image_size,
                            'num_sats': num_sats,
                            'strategy': strategy_name,
                            'policy': policy
                        })
            except Exception as e:
                continue
    
    return configs


def get_contacted_satellites(strategy_folder: Path, policy: str) -> Tuple[Set[str], int]:
    """Get the set of unique satellite IDs that were contacted"""
    zip_path = strategy_folder / 'simulation_logs.zip'
    
    if not zip_path.exists():
        return set(), 0
    
    contacted_sats = set()
    total_sats = 0
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            downlink_file = f'{policy}/meas-downlink-tx-rx.csv'
            
            if downlink_file not in zip_ref.namelist():
                return set(), 0
            
            with zip_ref.open(downlink_file) as f:
                df = pd.read_csv(f)
                
                if 'downlink-tx-rx' not in df.columns:
                    return set(), 0
                
                connected_df = df[df['downlink-tx-rx'] != 'None'].dropna(subset=['downlink-tx-rx'])
                
                for link in connected_df['downlink-tx-rx']:
                    if isinstance(link, str) and '-' in link:
                        sat_id = link.split('-')[0]
                        contacted_sats.add(sat_id)
            
            # Get total constellation size
            buffer_files = [f for f in zip_ref.namelist() if 'meas-MB-buffered-sat-' in f]
            all_sat_ids = set()
            for filename in buffer_files:
                parts = filename.split('sat-')
                if len(parts) > 1:
                    sat_id = parts[1].replace('.csv', '')
                    all_sat_ids.add(sat_id)
            
            total_sats = len(all_sat_ids)
                
    except Exception as e:
        return set(), 0
    
    return contacted_sats, total_sats


def calculate_utilization_for_all(configs: List[Dict]) -> Dict:
    """Calculate utilization percentages for all configurations"""
    results = {}
    
    for config in configs:
        image_size = config['image_size']
        strategy = config['strategy']
        num_sats = config['num_sats']
        policy = config['policy']
        strategy_folder = config['strategy_folder']
        
        if strategy not in results:
            results[strategy] = {}
        if policy not in results[strategy]:
            results[strategy][policy] = {}
        if num_sats not in results[strategy][policy]:
            results[strategy][policy][num_sats] = {}
        
        contacted_sats, total_sats = get_contacted_satellites(strategy_folder, policy)
        
        utilized_pct = (len(contacted_sats) / total_sats * 100) if total_sats > 0 else 0
        starved_pct = 100 - utilized_pct
        
        results[strategy][policy][num_sats][image_size] = {
            'utilized_pct': utilized_pct,
            'starved_pct': starved_pct,
            'contacted': len(contacted_sats),
            'total': total_sats
        }
    
    return results


def plot_utilization_stacked_chart(results: Dict, const_size: int, img_size: int):
    """Create stacked bar chart showing utilized vs starved satellites"""
    
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    fig, ax = plt.subplots(figsize=(16, 10))
    
    strategies = ["close-spaced", "frame-spaced", "orbit-spaced", "close-orbit-spaced"]
    
    bar_positions = []
    bar_labels = []
    utilized_pcts = []
    starved_pcts = []
    
    x_pos = 0
    bar_width = 0.6
    
    for strategy in strategies:
        if strategy not in results:
            continue
        
        for policy in POLICIES:
            if policy not in results[strategy]:
                continue
            
            if const_size not in results[strategy][policy]:
                continue
            
            if img_size not in results[strategy][policy][const_size]:
                continue
            
            data = results[strategy][policy][const_size][img_size]
            
            bar_positions.append(x_pos)
            bar_labels.append(f"{STRATEGIES_MAP[strategy]}\n{policy.upper()}")
            utilized_pcts.append(data['utilized_pct'])
            starved_pcts.append(data['starved_pct'])
            
            x_pos += bar_width + 0.2
        
        # Add spacing between strategies
        x_pos += 1.0
    
    # Create stacked bars
    ax.bar(bar_positions, utilized_pcts, bar_width, 
           label='Utilized (Contacted at least once)', color='#2ca02c', alpha=0.8)
    ax.bar(bar_positions, starved_pcts, bar_width, bottom=utilized_pcts,
           label='Starved (Never contacted)', color='#999999', alpha=0.6)
    
    # Add percentage labels
    for i, (utilized, starved) in enumerate(zip(utilized_pcts, starved_pcts)):
        # Utilized label
        if utilized > 5:
            ax.text(bar_positions[i], utilized/2, f'{utilized:.1f}%',
                   ha='center', va='center', fontsize=9, fontweight='bold', color='white')
        # Starved label
        if starved > 5:
            ax.text(bar_positions[i], utilized + starved/2, f'{starved:.1f}%',
                   ha='center', va='center', fontsize=9, fontweight='bold', color='white')
    
    ax.set_xticks(bar_positions)
    ax.set_xticklabels(bar_labels, rotation=45, ha='right', fontsize=9)
    ax.set_ylabel('Percentage of Constellation (%)', fontsize=14, fontweight='bold')
    ax.set_title(f'Satellite Utilization: Utilized vs Starved Satellites\n'
                f'{const_size}-Satellite Constellation | {IMAGE_SIZES.get(img_size, f"{img_size}KB")} Image Size\n'
                f'Shows satellite-level contention and resource waste',
                fontsize=16, fontweight='bold', pad=20)
    
    ax.set_ylim(0, 105)
    ax.axhline(y=50, color='gray', linestyle='--', linewidth=1, alpha=0.5)
    ax.legend(loc='upper right', fontsize=12)
    ax.grid(axis='y', alpha=0.3)
    
    # Add annotations highlighting severe starvation
    max_starved = max(starved_pcts) if starved_pcts else 0
    if max_starved > 70:
        ax.text(0.02, 0.98, 
               f'⚠️ Close shows severe satellite starvation!\n'
               f'Up to {max_starved:.0f}% of satellites NEVER used',
               transform=ax.transAxes,
               fontsize=11, 
               verticalalignment='top',
               bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8),
               fontweight='bold')
    
    plt.tight_layout()
    
    output_file = OUTPUT_DIR / f'satellite_utilization_stacked_{const_size}sats_{img_size}kb.png'
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"✅ Saved: {output_file}")
    plt.close()


def main():
    print("=" * 80)
    print("SATELLITE UTILIZATION ANALYSIS (Stacked Bars)")
    print("=" * 80)
    
    configs = scan_all_configurations()
    print(f"✅ Found {len(configs)} configurations\n")
    
    print("Calculating satellite utilization statistics...")
    results = calculate_utilization_for_all(configs)
    
    print("\nGenerating charts for all constellation sizes and image sizes...")
    
    # Generate charts for all combinations
    for const_size in CONSTELLATION_SIZES:
        for img_size in IMAGE_SIZES.keys():
            # Check if we have data for this combination
            has_data = False
            for strategy in results.values():
                for policy in strategy.values():
                    if const_size in policy and img_size in policy[const_size]:
                        has_data = True
                        break
                if has_data:
                    break
            
            if has_data:
                print(f"  Generating: {const_size} sats, {IMAGE_SIZES[img_size]}")
                plot_utilization_stacked_chart(results, const_size, img_size)
    
    print("\n" + "=" * 80)
    print("✅ COMPLETE!")
    print("=" * 80)
    print(f"\n📁 All charts saved to: {OUTPUT_DIR}/")


if __name__ == '__main__':
    main()
