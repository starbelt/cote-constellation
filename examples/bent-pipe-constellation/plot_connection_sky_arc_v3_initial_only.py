#!/usr/bin/env python3
"""
Generate connection sky arc plots showing ONLY initial connection points.

Plots only the first timestep when switching to a new satellite (sat_id changes).
This shows WHERE satellites are when they're first selected for download.

Ground station at origin (0,0), satellites arc overhead from left (west) to right (east).

For each configuration (image size, spacing strategy, satellite count):
- Creates one PNG with 4 subplots (2x2 grid), one per policy
- Each subplot: arc plot showing initial connection points only
  - X-axis: Signed horizontal distance (-1800 to +1800 km) - negative = west/approaching, positive = east/departing
  - Y-axis: Altitude/height above ground station (km)
  - Each dot: The FIRST timestep when switching to a different satellite
  - Shows where satellites are when first selected

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
from math import radians, cos, sin, atan2, degrees

# Configuration
BASE_RESULTS_DIR = Path("results/base results 2")
OUTPUT_DIR = Path("connection_sky_arc_charts_initial")
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

# Ground station location (Svalbard)
GS_LAT = 78.2308
GS_LON = 15.3906

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

def calculate_bearing(lat1, lon1, lat2, lon2):
    """
    Calculate bearing from point 1 to point 2 in degrees.
    Returns angle from -180 to +180 where:
    - Positive = satellite is east of ground station
    - Negative = satellite is west of ground station
    """
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    
    dlon = lon2 - lon1
    
    x = sin(dlon) * cos(lat2)
    y = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(dlon)
    
    bearing_rad = atan2(x, y)
    bearing_deg = degrees(bearing_rad)
    
    return bearing_deg

def calculate_ground_track_position(elevation_deg, distance_km, sat_lat, sat_lon):
    """
    Calculate signed horizontal position along ground track from elevation, distance, and sat position.
    
    Args:
        elevation_deg: Elevation angle from ground station to satellite
        distance_km: Slant range distance from ground station to satellite
        sat_lat: Satellite latitude
        sat_lon: Satellite longitude
    
    Returns:
        x: Signed horizontal distance from GS (negative = west/approaching, positive = east/departing)
        y: Altitude above ground
    """
    # Convert to radians
    elev_rad = np.radians(elevation_deg)
    
    # Calculate altitude (y-axis) - always positive
    altitude = distance_km * np.sin(elev_rad)
    
    # Calculate horizontal distance magnitude
    horizontal_dist = distance_km * np.cos(elev_rad)
    
    # Determine sign based on bearing from ground station to satellite
    bearing = calculate_bearing(GS_LAT, GS_LON, sat_lat, sat_lon)
    
    # Use bearing to determine if satellite is left (negative) or right (positive)
    signed_horizontal = horizontal_dist * np.sign(bearing)
    
    return signed_horizontal, altitude

def load_initial_connection_points(analysis_dir, spacing, policy):
    """Load ONLY initial connection points - first timestep when sat_id changes."""
    zip_path = analysis_dir / spacing / "simulation_logs.zip"
    
    if not zip_path.exists():
        return None, {}
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            vis_log_file = f"{policy}/visibility_log.csv"
            
            try:
                with zip_ref.open(vis_log_file) as f:
                    df = pd.read_csv(f)
                    
                    # Filter to only rows where download is happening
                    download_df = df[df['downloaded_mb'] > 0].copy()
                    
                    if len(download_df) == 0:
                        return None, {}
                    
                    # Check for required columns
                    required_cols = ['elevation_deg', 'distance_km', 'lat_deg', 'lon_deg', 'sat_id', 'time', 'downloaded_mb']
                    if not all(col in download_df.columns for col in required_cols):
                        print(f"    ⚠️  Missing required columns in {policy}")
                        return None, {}
                    
                    # Sort by time to ensure proper ordering
                    download_df = download_df.sort_values('time').reset_index(drop=True)
                    
                    # Calculate total data downloaded
                    total_data_mb = download_df['downloaded_mb'].sum()
                    
                    # Extract ONLY the first timestep when sat_id changes and track connection times
                    initial_connections = []
                    prev_sat_id = None
                    prev_time = None
                    num_connections = 0
                    connection_times = []
                    
                    for idx, row in download_df.iterrows():
                        if row['sat_id'] != prev_sat_id:
                            # Calculate time since last connection switch
                            if prev_time is not None:
                                connection_time = row['time'] - prev_time
                                connection_times.append(connection_time)
                            
                            # This is the first time we're connecting to this satellite
                            num_connections += 1
                            
                            # Calculate position
                            x, y = calculate_ground_track_position(
                                row['elevation_deg'], 
                                row['distance_km'],
                                row['lat_deg'],
                                row['lon_deg']
                            )
                            
                            initial_connections.append({
                                'x': x, 
                                'y': y, 
                                'elevation': row['elevation_deg'],
                                'lat': row['lat_deg'],
                                'lon': row['lon_deg'],
                                'sat_id': row['sat_id']
                            })
                            
                            prev_sat_id = row['sat_id']
                            prev_time = row['time']
                    
                    if len(initial_connections) == 0:
                        return None, {}
                    
                    # Calculate average connection time
                    avg_connection_time = np.mean(connection_times) if connection_times else 0
                    
                    # Create statistics dictionary
                    stats = {
                        'num_connections': num_connections,
                        'avg_connection_time': avg_connection_time,
                        'total_data_mb': total_data_mb
                    }
                    
                    return pd.DataFrame(initial_connections), stats
                        
            except KeyError:
                print(f"    ⚠️  File {vis_log_file} not found in zip")
                return None, {}
                
    except Exception as e:
        print(f"    ⚠️  Error loading {policy}: {e}")
        return None, {}

def create_sky_arc_plot(image_size_code, image_size_mb, spacing, sat_count):
    """Create 2x2 sky arc plot for all 4 policies - INITIAL CONNECTIONS ONLY."""
    analysis_dir = find_analysis_dir(image_size_code, sat_count)
    
    if not analysis_dir:
        print(f"  ⚠️  No analysis directory found for {spacing}, {sat_count} sats, {image_size_mb} MB")
        return
    
    # Load data for all policies
    policy_data = {}
    policy_stats = {}
    for policy in POLICIES:
        data, stats = load_initial_connection_points(analysis_dir, spacing, policy)
        if data is not None:
            policy_data[policy] = data
            policy_stats[policy] = stats
    
    if not policy_data:
        print(f"  ⚠️  No data found for any policy: {spacing}, {sat_count} sats, {image_size_mb} MB")
        return
    
    # Create figure with 2x2 subplots
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle(f'{STRATEGY_LABELS[spacing]} - {sat_count} Satellites - {image_size_mb} MB Image\n'
                 f'Sky Arc View - INITIAL CONNECTION POINTS ONLY (GS at Origin)', 
                 fontsize=14, fontweight='bold')
    
    # Plot each policy
    for idx, policy in enumerate(POLICIES):
        row = idx // 2
        col = idx % 2
        ax = axes[row, col]
        
        if policy in policy_data:
            data = policy_data[policy]
            
            # Scatter plot: x = signed horizontal distance, y = altitude
            # Color by elevation
            scatter = ax.scatter(data['x'], data['y'], 
                               c=data['elevation'], 
                               cmap='viridis', 
                               alpha=0.7, 
                               s=40,
                               edgecolors='black',
                               linewidths=0.5)
            
            # Add colorbar
            plt.colorbar(scatter, ax=ax, label='Elevation (deg)')
            
            # Mark ground station at origin with antenna icon
            # Draw a ground station antenna dish (parabolic antenna)
            # Base/building
            ax.plot(0, -30, marker='s', color='darkred', markersize=10, zorder=5)
            # Tower/mast
            ax.plot([0, 0], [-30, 20], color='darkred', linewidth=3, zorder=5)
            # Dish (triangle representing parabolic dish)
            ax.plot(0, 30, marker='v', color='red', markersize=20, markeredgecolor='darkred', 
                   markeredgewidth=2, label='Ground Station', zorder=5)
            
            # Add ground level line
            ax.axhline(y=0, color='brown', linestyle='-', linewidth=2, alpha=0.3, label='Ground Level')
            
            # Get statistics from policy_stats
            stats = policy_stats[policy]
            num_connections = stats['num_connections']
            avg_connection_time = stats['avg_connection_time']
            total_data_mb = stats['total_data_mb']
            
            # Calculate altitude statistics
            avg_altitude = data['y'].mean()
            max_altitude = data['y'].max()
            min_altitude = data['y'].min()
            avg_elevation = data['elevation'].mean()
            
            # Add statistics box
            stats_text = f'Connections: {num_connections}\n'
            stats_text += f'Avg Connection Time: {avg_connection_time:.1f}s\n'
            stats_text += f'Data Downloaded: {total_data_mb:.2f} MB\n'
            stats_text += f'Avg Elevation: {avg_elevation:.1f}°\n'
            stats_text += f'Avg Altitude: {avg_altitude:.1f} km\n'
            stats_text += f'Max Altitude: {max_altitude:.1f} km\n'
            stats_text += f'Min Altitude: {min_altitude:.1f} km'
            
            ax.text(0.02, 0.98, stats_text,
                   transform=ax.transAxes,
                   fontsize=9,
                   verticalalignment='top',
                   bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.7))
        
        else:
            ax.text(0.5, 0.5, 'No data available', 
                   ha='center', va='center', fontsize=12, color='gray')
        
        # Formatting
        ax.set_xlabel('Horizontal Distance from GS (km)\n← West/Approaching | East/Departing →', fontsize=10)
        ax.set_ylabel('Altitude Above Ground (km)', fontsize=10)
        ax.set_title(f'{policy.upper()} Policy', fontsize=11, fontweight='bold')
        ax.grid(True, alpha=0.3)
        ax.set_aspect('equal', adjustable='datalim')
        
        # Set consistent x-axis limits for comparison
        ax.set_xlim(-1800, 1800)
        
    plt.tight_layout()
    
    # Save plot
    output_path = OUTPUT_DIR / spacing / f"{spacing}_{sat_count}sats_{image_size_code}mb_skyarc_initial.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    
    print(f"  ✅ Saved: {output_path}")

def main():
    """Generate all sky arc plots - initial connections only."""
    print("=" * 80)
    print("CONNECTION SKY ARC PLOTS - INITIAL CONNECTION POINTS ONLY")
    print("=" * 80)
    
    # Count total charts to generate
    total = len(IMAGE_SIZES) * len(SPACING_STRATEGIES) * len(SAT_COUNTS)
    print(f"\nTotal charts to generate: {total}")
    print(f"Ground Station: Svalbard ({GS_LAT}°N, {GS_LON}°E)")
    print(f"Plotting ONLY first timestep when sat_id changes (initial connection points)\n")
    
    count = 0
    for image_code, image_mb in IMAGE_SIZES.items():
        for spacing in SPACING_STRATEGIES:
            for sat_count in SAT_COUNTS:
                count += 1
                print(f"[{count}/{total}] Creating chart: {spacing}, {sat_count} sats, {image_mb} MB")
                create_sky_arc_plot(image_code, image_mb, spacing, sat_count)
    
    print("\n" + "=" * 80)
    print(f"✅ COMPLETE! Generated {count} sky arc charts (initial only) in {OUTPUT_DIR}/")
    print("=" * 80)

if __name__ == "__main__":
    main()
