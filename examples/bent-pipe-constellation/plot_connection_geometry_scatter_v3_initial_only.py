#!/usr/bin/env python3
"""
Generate connection geometry scatter plots showing ONLY initial connection points.

Plots only the first timestep when switching to a new satellite (sat_id changes).
This shows WHERE satellites are in elevation/distance space when first selected for download.

For each configuration (image size, spacing strategy, satellite count):
- Creates one PNG with 4 subplots (2x2 grid), one per policy
- Each subplot: scatter plot of initial connection points only
  - X-axis: Distance from ground station (km)
  - Y-axis: Elevation angle (degrees)
  - Each dot: The FIRST timestep when switching to a different satellite

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
BASE_RESULTS_DIR = BASE_DIR / "results" / "base results 2"
OUTPUT_DIR = Path("constellation_analysis") / "connection_geometry_charts_initial"
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

def load_initial_connection_geometry(analysis_dir, spacing, policy):
    """Load ONLY initial connection points - first timestep when sat_id changes."""
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
                    
                    # Extract ONLY the first timestep when sat_id changes
                    initial_connections = []
                    prev_sat_id = None
                    num_connections = 0
                    
                    for idx, row in download_df.iterrows():
                        if row['sat_id'] != prev_sat_id:
                            # This is the first time we're connecting to this satellite
                            num_connections += 1
                            initial_connections.append({
                                'elevation_deg': row['elevation_deg'],
                                'distance_km': row['distance_km'],
                                'sat_id': row['sat_id']
                            })
                            prev_sat_id = row['sat_id']
                    
                    if len(initial_connections) == 0:
                        return None, 0
                    
                    # Return initial connection points and count
                    return pd.DataFrame(initial_connections), num_connections
                        
            except KeyError:
                print(f"    ⚠️  File {vis_log_file} not found in zip")
                return None, 0
                
    except Exception as e:
        print(f"    ⚠️  Error reading {zip_path}: {e}")
        return None, 0

def create_geometry_scatter(image_size_code, image_size_mb, spacing, sat_count):
    """Create 2x2 scatter plot grid for all 4 policies - INITIAL CONNECTIONS ONLY."""
    
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
                 f'Connection Geometry - INITIAL CONNECTION POINTS ONLY',
                 fontsize=16, fontweight='bold', y=0.995)
    
    # Flatten axes for easier iteration
    axes_flat = axes.flatten()
    
    has_data = False
    
    for idx, policy in enumerate(POLICIES):
        ax = axes_flat[idx]
        
        # Load initial connection geometry data
        data, num_connections = load_initial_connection_geometry(analysis_dir, spacing, policy)
        
        if data is not None and len(data) > 0:
            has_data = True
            
            # Create scatter plot
            ax.scatter(data['distance_km'], data['elevation_deg'], 
                      alpha=0.6, s=40, c='#2E86AB', edgecolors='black', linewidths=0.5)
            
            # Add ground station at origin
            ax.axvline(x=0, color='red', linestyle='--', linewidth=2, alpha=0.7, label='Ground Station')
            
            # Statistics
            mean_elev = data['elevation_deg'].mean()
            mean_dist = data['distance_km'].mean()
            
            # Add stats text box
            stats_text = f'Initial Connections: {num_connections:,}\n'
            stats_text += f'Avg Elev: {mean_elev:.1f}°\n'
            stats_text += f'Avg Dist: {mean_dist:.1f} km'
            
            ax.text(0.02, 0.98, stats_text,
                   transform=ax.transAxes,
                   verticalalignment='top',
                   bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.8),
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
        print(f"    ⚠️  No data for any policy")
        plt.close()
        return False
    
    plt.tight_layout()
    
    # Save the figure
    output_path = OUTPUT_DIR / spacing / f"{spacing}_{sat_count}sats_{image_size_code}mb_initial.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    
    print(f"  ✅ Saved: {output_path}")
    return True

def main():
    """Generate all geometry scatter plots - initial connections only."""
    print("=" * 80)
    print("CONNECTION GEOMETRY SCATTER PLOTS - INITIAL CONNECTION POINTS ONLY")
    print("=" * 80)
    print("\nPlotting ONLY first timestep when sat_id changes (initial connection points)")
    print(f"Output directory: {OUTPUT_DIR}\n")
    
    success_count = 0
    total_count = 0
    
    for image_code, image_mb in IMAGE_SIZES.items():
        print(f"\n{'='*60}")
        print(f"Image Size: {image_mb} MB ({image_code})")
        print(f"{'='*60}")
        
        for spacing in SPACING_STRATEGIES:
            print(f"\n{spacing}:")
            for sat_count in SAT_COUNTS:
                total_count += 1
                if create_geometry_scatter(image_code, image_mb, spacing, sat_count):
                    success_count += 1
    
    print("\n" + "=" * 80)
    print(f"✅ COMPLETE!")
    print(f"Successfully generated {success_count}/{total_count} charts")
    print(f"Output directory: {OUTPUT_DIR}/")
    print("=" * 80)

if __name__ == "__main__":
    main()
