#!/usr/bin/env python3
"""
Generate connection sky arc plots showing the geometric path of satellites overhead.

Visualizes satellite passes as arcs across the sky, with download events marked.
Ground station at origin (0,0), satellites arc overhead.

For each configuration (image size, spacing strategy, satellite count):
- Creates one PNG with 4 subplots (2x2 grid), one per policy
- Each subplot: arc plot showing satellite paths and where downloads occur
  - X-axis: Horizontal distance along ground track (km) - negative = approaching, positive = receding
  - Y-axis: Altitude/height above ground station (km)
  - Each dot: A timestep where downloaded_mb > 0
  - Shows the actual curved trajectory satellites take overhead

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
BASE_RESULTS_DIR = Path("results/base results 2")
OUTPUT_DIR = Path("connection_sky_arc_charts")
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

# Earth radius (km) for calculations
EARTH_RADIUS = 6371.0

def find_analysis_dir(image_size_code, sat_count):
    """Find analysis directory for given configuration."""
    pattern = f"constellation_analysis_*_{image_size_code}_{sat_count:02d}"
    matching = list(BASE_RESULTS_DIR.glob(pattern))
    return matching[0] if matching else None

def calculate_ground_track_position(elevation_deg, distance_km):
    """
    Calculate horizontal position along ground track from elevation and slant distance.
    
    Returns:
        x: horizontal distance from GS (negative = approaching, positive = receding)
        y: altitude above ground
    """
    # Convert to radians
    elev_rad = np.radians(elevation_deg)
    
    # For simplicity, we'll use a geometric approximation:
    # Altitude = distance * sin(elevation)
    # Horizontal distance = distance * cos(elevation)
    
    altitude = distance_km * np.sin(elev_rad)
    horizontal_dist = distance_km * np.cos(elev_rad)
    
    return horizontal_dist, altitude

def load_connection_sky_arc(analysis_dir, spacing, policy):
    """Load position data for download events to show arc pattern."""
    zip_path = analysis_dir / spacing / "simulation_logs.zip"
    
    if not zip_path.exists():
        return None
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            vis_log_file = f"{policy}/visibility_log.csv"
            
            try:
                with zip_ref.open(vis_log_file) as f:
                    df = pd.read_csv(f)
                    
                    # Filter to only rows where download is happening
                    download_df = df[df['downloaded_mb'] > 0].copy()
                    
                    if len(download_df) == 0:
                        return None
                    
                    # Check which columns exist
                    if 'elevation_deg' not in download_df.columns or 'distance_km' not in download_df.columns:
                        print(f"    ⚠️  Missing elevation or distance columns in {policy}")
                        return None
                    
                    # Calculate ground track position
                    positions = []
                    for _, row in download_df.iterrows():
                        x, y = calculate_ground_track_position(row['elevation_deg'], row['distance_km'])
                        positions.append({'x': x, 'y': y, 'elevation': row['elevation_deg']})
                    
                    return pd.DataFrame(positions)
                        
            except KeyError:
                print(f"    ⚠️  File {vis_log_file} not found in zip")
                return None
                
    except Exception as e:
        print(f"    ⚠️  Error reading {zip_path}: {e}")
        return None

def create_sky_arc_plot(image_size_code, image_size_mb, spacing, sat_count):
    """Create 2x2 sky arc plot grid for all 4 policies."""
    
    print(f"\n  Creating sky arc chart: {spacing}, {sat_count} sats, {image_size_mb} MB")
    
    analysis_dir = find_analysis_dir(image_size_code, sat_count)
    
    if not analysis_dir:
        print(f"    ⚠️  Analysis directory not found")
        return False
    
    # Check if spacing strategy exists
    if not (analysis_dir / spacing / "simulation_logs.zip").exists():
        print(f"    ⚠️  Spacing strategy {spacing} not found")
        return False
    
    # Create figure with 2x2 subplots
    fig, axes = plt.subplots(2, 2, figsize=(18, 14))
    fig.suptitle(f'{STRATEGY_LABELS[spacing]} - {sat_count} Satellites - {image_size_mb} MB Images\n'
                 f'Sky Arc View: Download Events on Satellite Overhead Paths',
                 fontsize=16, fontweight='bold', y=0.995)
    
    # Flatten axes for easier iteration
    axes_flat = axes.flatten()
    
    has_data = False
    
    for idx, policy in enumerate(POLICIES):
        ax = axes_flat[idx]
        
        # Load connection arc data
        data = load_connection_sky_arc(analysis_dir, spacing, policy)
        
        if data is not None and len(data) > 0:
            has_data = True
            
            # Create scatter plot showing the arc
            # Use color to show elevation (darker = lower, lighter = higher)
            scatter = ax.scatter(data['x'], data['y'], 
                                c=data['elevation'], cmap='viridis',
                                alpha=0.6, s=20, edgecolors='black', linewidth=0.5)
            
            # Add colorbar for elevation
            cbar = plt.colorbar(scatter, ax=ax, label='Elevation (degrees)', pad=0.02)
            cbar.ax.tick_params(labelsize=9)
            
            # Ground station at origin
            ax.plot(0, 0, 'r*', markersize=20, label='Ground Station', zorder=10)
            
            # Add ground line
            x_range = ax.get_xlim()
            ax.axhline(y=0, color='brown', linestyle='-', linewidth=2, alpha=0.5, label='Ground Level')
            
            # Add vertical line through GS
            ax.axvline(x=0, color='red', linestyle='--', linewidth=1.5, alpha=0.5)
            
            # Statistics
            num_connections = len(data)
            mean_elev = data['elevation'].mean()
            max_altitude = data['y'].max()
            x_span = data['x'].max() - data['x'].min()
            
            # Add stats text box
            stats_text = f'Downloads: {num_connections:,}\n'
            stats_text += f'Avg Elev: {mean_elev:.1f}°\n'
            stats_text += f'Max Alt: {max_altitude:.1f} km\n'
            stats_text += f'Track Span: {x_span:.1f} km'
            
            ax.text(0.02, 0.98, stats_text,
                   transform=ax.transAxes,
                   verticalalignment='top',
                   bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8),
                   fontsize=9)
            
            ax.set_xlabel('Horizontal Distance from GS (km)\n← Approaching | Overhead | Receding →', 
                         fontsize=11, fontweight='bold')
            ax.set_ylabel('Altitude Above Ground (km)', fontsize=11, fontweight='bold')
            ax.set_title(f'{policy.upper()} Policy', fontsize=13, fontweight='bold', pad=10)
            ax.grid(True, alpha=0.3)
            ax.legend(loc='upper right', fontsize=9)
            
            # Set aspect ratio to show arcs nicely
            ax.set_aspect('equal', adjustable='datalim')
            
        else:
            # No data
            ax.text(0.5, 0.5, 'No Download Data',
                   transform=ax.transAxes,
                   ha='center', va='center',
                   fontsize=14, color='gray')
            ax.set_xlabel('Horizontal Distance from GS (km)\n← Approaching | Overhead | Receding →', 
                         fontsize=11, fontweight='bold')
            ax.set_ylabel('Altitude Above Ground (km)', fontsize=11, fontweight='bold')
            ax.set_title(f'{policy.upper()} Policy', fontsize=13, fontweight='bold', pad=10)
            ax.grid(True, alpha=0.3)
            ax.plot(0, 0, 'r*', markersize=20, label='Ground Station')
            ax.axhline(y=0, color='brown', linestyle='-', linewidth=2, alpha=0.5, label='Ground Level')
            ax.legend(loc='upper right', fontsize=9)
    
    if not has_data:
        print(f"    ⚠️  No data found for any policy")
        plt.close()
        return False
    
    plt.tight_layout()
    
    # Save
    output_file = OUTPUT_DIR / spacing / f"{spacing}_{sat_count}sats_{image_size_code}mb_skyarc.png"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"    ✅ Saved: {output_file}")
    plt.close()
    
    return True

def main():
    """Generate all connection sky arc plots."""
    
    print("=" * 80)
    print("CONNECTION SKY ARC PLOTS")
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
                if create_sky_arc_plot(image_size_code, image_size_mb, spacing, sat_count):
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
