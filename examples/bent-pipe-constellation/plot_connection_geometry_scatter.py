#!/usr/bin/env python3
"""
Generate connection geometry scatter plots showing where downloads occur in elevation/distance space.

For each configuration (image size, spacing strategy, satellite count):
- Creates one PNG with 4 subplots (2x2 grid), one per policy
- Each subplot: scatter plot of download events
  - X-axis: Distance from ground station (km)
  - Y-axis: Elevation angle (degrees)
  - Each dot: A timestep where downloaded_mb > 0

Data source: results/base results 2
Satellite counts: 1, 25, 50, 100, 200
Spacing strategies: close-spaced, orbit-spaced, frame-spaced, close-orbit-spaced
Policies: sticky, fifo, roundrobin, random
Image sizes: 00027, 00279, 02799, 28000, 280000, 1024000
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
import zipfile
import re

# Configuration
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = Path("constellation_analysis") / "connection_geometry_charts"
SAT_COUNTS = [1, 25, 50, 100, 200]
SPACING_STRATEGIES = ['close-spaced', 'orbit-spaced', 'frame-spaced', 'close-orbit-spaced']
POLICIES = ['sticky', 'fifo', 'roundrobin', 'random']
IMAGE_SIZES = {
    '00027': 0.027,
    '00279': 0.279,
    '02799': 2.799,
    '28000': 28.0,
    '280000': 280.0,
    '1024000': 1024.0
}

# Strategy labels
STRATEGY_LABELS = {
    'close-spaced': 'Close-Spaced',
    'orbit-spaced': 'Orbit-Spaced',
    'frame-spaced': 'Frame-Spaced',
    'close-orbit-spaced': 'Close-Orbit-Spaced'
}

def find_analysis_dir(image_size_code, sat_count):
    """Find analysis directory for given configuration."""
    pattern = f"constellation_analysis_*_{image_size_code}_{sat_count:02d}"
    matching = list(BASE_RESULTS_DIR.glob(pattern))
    return matching[0] if matching else None

def load_connection_geometry(analysis_dir, spacing, policy):
    """Load elevation and distance data for download events."""
    zip_path = analysis_dir / spacing / "simulation_logs.zip"
    
    if not zip_path.exists():
        return None, 0
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            vis_log_file = f"{policy}/visibility_log.csv"
            
            try:
                with zip_ref.open(vis_log_file) as f:
                    df = pd.read_csv(f)
                    
                    # Filter to only rows where download is happening
                    download_df = df[df['downloaded_mb'] > 0].copy()
                    
                    if len(download_df) == 0:
                        return None, 0
                    
                    # Check required columns
                    required_cols = ['elevation_deg', 'distance_km', 'sat_id', 'time']
                    if not all(col in download_df.columns for col in required_cols):
                        print(f"    ⚠️  Missing required columns in {policy}")
                        return None, 0
                    
                    # Sort by time to ensure proper ordering
                    download_df = download_df.sort_values('time').reset_index(drop=True)
                    
                    # Count unique satellite connections (only count when sat_id changes)
                    num_connections = 0
                    prev_sat_id = None
                    for sat_id in download_df['sat_id']:
                        if sat_id != prev_sat_id:
                            num_connections += 1
                            prev_sat_id = sat_id
                    
                    # Return elevation, distance data and connection count
                    return download_df[['elevation_deg', 'distance_km']], num_connections
                        
            except KeyError:
                print(f"    ⚠️  File {vis_log_file} not found in zip")
                return None, 0
                
    except Exception as e:
        print(f"    ⚠️  Error reading {zip_path}: {e}")
        return None, 0

def create_geometry_scatter(image_size_code, image_size_mb, spacing, sat_count):
    """Create 2x2 scatter plot grid for all 4 policies."""
    
    print(f"\n  Creating chart: {spacing}, {sat_count} sats, {image_size_mb} MB")
    
    analysis_dir = find_analysis_dir(image_size_code, sat_count)
    
    if not analysis_dir:
        print(f"    ⚠️  Analysis directory not found")
        return False
    
    # Check if spacing strategy exists
    if not (analysis_dir / spacing / "simulation_logs.zip").exists():
        print(f"    ⚠️  Spacing strategy {spacing} not found")
        return False
    
    # Create figure with 2x2 subplots
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle(f'{STRATEGY_LABELS[spacing]} - {sat_count} Satellites - {image_size_mb} MB Images\n'
                 f'Connection Geometry: Download Events in Elevation/Distance Space',
                 fontsize=16, fontweight='bold', y=0.995)
    
    # Flatten axes for easier iteration
    axes_flat = axes.flatten()
    
    has_data = False
    
    for idx, policy in enumerate(POLICIES):
        ax = axes_flat[idx]
        
        # Load connection geometry data
        data, num_connections = load_connection_geometry(analysis_dir, spacing, policy)
        
        if data is not None and len(data) > 0:
            has_data = True
            
            # Create scatter plot
            ax.scatter(data['distance_km'], data['elevation_deg'], 
                      alpha=0.3, s=10, c='#2E86AB', edgecolors='none')
            
            # Add ground station at origin
            ax.axvline(x=0, color='red', linestyle='--', linewidth=2, alpha=0.7, label='Ground Station')
            
            # Statistics
            num_download_events = len(data)
            mean_elev = data['elevation_deg'].mean()
            mean_dist = data['distance_km'].mean()
            
            # Add stats text box
            stats_text = f'Connections: {num_connections:,}\n'
            stats_text += f'Download Events: {num_download_events:,}\n'
            stats_text += f'Avg Elev: {mean_elev:.1f}°\n'
            stats_text += f'Avg Dist: {mean_dist:.1f} km'
            
            ax.text(0.02, 0.98, stats_text,
                   transform=ax.transAxes,
                   verticalalignment='top',
                   bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8),
                   fontsize=9)
            
            ax.set_xlabel('Distance from Ground Station (km)', fontsize=11, fontweight='bold')
            ax.set_ylabel('Elevation Angle (degrees)', fontsize=11, fontweight='bold')
            ax.set_title(f'{policy.upper()} Policy', fontsize=13, fontweight='bold', pad=10)
            ax.grid(True, alpha=0.3)
            ax.legend(loc='upper right', fontsize=9)
            
        else:
            # No data
            ax.text(0.5, 0.5, 'No Download Data',
                   transform=ax.transAxes,
                   ha='center', va='center',
                   fontsize=14, color='gray')
            ax.set_xlabel('Distance from Ground Station (km)', fontsize=11, fontweight='bold')
            ax.set_ylabel('Elevation Angle (degrees)', fontsize=11, fontweight='bold')
            ax.set_title(f'{policy.upper()} Policy', fontsize=13, fontweight='bold', pad=10)
            ax.grid(True, alpha=0.3)
    
    if not has_data:
        print(f"    ⚠️  No data found for any policy")
        plt.close()
        return False
    
    plt.tight_layout()
    
    # Save
    output_file = OUTPUT_DIR / spacing / f"{spacing}_{sat_count}sats_{image_size_code}mb.png"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"    ✅ Saved: {output_file}")
    plt.close()
    
    return True

def main():
    """Generate all connection geometry scatter plots."""
    
    print("=" * 80)
    print("CONNECTION GEOMETRY SCATTER PLOTS")
    print("=" * 80)
    print(f"Data source: {BASE_RESULTS_DIR}")
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Satellite counts: {SAT_COUNTS}")
    print(f"Spacing strategies: {SPACING_STRATEGIES}")
    print(f"Policies: {POLICIES}")
    print(f"Image sizes: {list(IMAGE_SIZES.keys())}")
    print()
    
    total = len(IMAGE_SIZES) * len(SPACING_STRATEGIES) * len(SAT_COUNTS)
    print(f"Total charts to generate: {total}")
    print("=" * 80)
    
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    successful = 0
    failed = 0
    
    for image_size_code, image_size_mb in IMAGE_SIZES.items():
        print(f"\n📷 Image Size: {image_size_mb} MB (code: {image_size_code})")
        
        for spacing in SPACING_STRATEGIES:
            print(f"\n  📡 Spacing: {STRATEGY_LABELS[spacing]}")
            
            for sat_count in SAT_COUNTS:
                if create_geometry_scatter(image_size_code, image_size_mb, spacing, sat_count):
                    successful += 1
                else:
                    failed += 1
    
    print("\n" + "=" * 80)
    print("GENERATION COMPLETE")
    print("=" * 80)
    print(f"✅ Successful: {successful}/{total}")
    print(f"❌ Failed: {failed}/{total}")
    print(f"\nOutput directory: {OUTPUT_DIR}/")
    print("=" * 80)

if __name__ == '__main__':
    import os
    
    # Change to script directory
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    main()
