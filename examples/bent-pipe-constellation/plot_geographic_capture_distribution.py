#!/usr/bin/env python3
"""
Geographic Capture Distribution - Strategy Comparison
======================================================
Analyzes geographic distribution of image captures aggregated by spacing strategy.
Since trigger events are independent of link policy and image size, we aggregate
all captures for each strategy to show the overall geographic pattern.

Generates:
1. Latitude histogram (bar chart) - one per strategy
2. World map with capture locations - one per strategy
"""

import zipfile
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import re
from collections import defaultdict

def scan_all_configurations():
    """Find all constellation_analysis_* folders and extract metadata."""
    configs = []
    pattern = re.compile(r'constellation_analysis_(\d{8}_\d{6})_(\d+)_(\d+)')
    
    for folder in sorted(Path('.').glob('constellation_analysis_*')):
        match = pattern.match(folder.name)
        if match:
            timestamp, image_code, sat_count = match.groups()
            
            # Map image code to actual size
            image_size_map = {
                '00027': '0.027mb',
                '00279': '0.279mb', 
                '02799': '2.799mb',
                '28000': '28.0mb'
            }
            image_size = image_size_map.get(image_code, f'{image_code}mb')
            sat_count_map = {'01': 1, '50': 50, '100': 100, '200': 200}
            sats = sat_count_map.get(sat_count, int(sat_count))
            
            configs.append({
                'folder': folder,
                'image_size': image_size,
                'sat_count': sats
            })
    
    return configs

def load_all_captures_for_strategy(configs, strategy, sat_count=None):
    """
    Load ALL capture locations for a given strategy and optional constellation size.
    Since triggers are independent of policy and image size, we aggregate across those dimensions.
    
    Args:
        configs: List of configuration dictionaries
        strategy: Spacing strategy name
        sat_count: Optional satellite count filter (1, 50, 100, or 200)
    """
    all_lats = []
    all_lons = []
    
    for config in configs:
        # Filter by constellation size if specified
        if sat_count is not None and config['sat_count'] != sat_count:
            continue
            
        strategy_dir = config['folder'] / strategy
        zip_path = strategy_dir / 'simulation_logs.zip'
        
        if not zip_path.exists():
            continue
        
        # Load from one policy (they should all have the same triggers)
        # We'll use 'sticky' as the reference
        try:
            with zipfile.ZipFile(zip_path) as z:
                csv_name = 'sticky/visibility_log.csv'
                with z.open(csv_name) as f:
                    df = pd.read_csv(f)
                    
                    # Filter for only rows where an image was taken
                    captures = df[df['image_taken'] == 1].copy()
                    
                    if len(captures) > 0:
                        lats = captures['lat_deg'].values
                        lons = captures['lon_deg'].values
                        
                        # Normalize longitude to -180 to 180 range
                        lons = ((lons + 180) % 360) - 180
                        
                        all_lats.extend(lats)
                        all_lons.extend(lons)
                        
        except Exception as e:
            print(f"⚠️  Warning: Could not read {strategy} from {config['folder'].name}: {e}")
            continue
    
    return np.array(all_lats), np.array(all_lons)

def create_latitude_histogram(lats, strategy, output_path):
    """Create a histogram showing capture distribution by latitude."""
    
    fig, ax = plt.subplots(figsize=(16, 8))
    
    # Create latitude bins (every 5 degrees)
    lat_bins = np.arange(-90, 95, 5)
    
    # Create histogram
    counts, edges, patches = ax.hist(lats, bins=lat_bins, color='steelblue', 
                                     edgecolor='black', linewidth=0.5, alpha=0.8)
    
    # Add value labels on top of bars
    for count, edge, patch in zip(counts, edges, patches):
        height = patch.get_height()
        if height > 0:
            ax.text(edge + 2.5, height, f'{int(height):,}',
                   ha='center', va='bottom', fontsize=8, fontweight='bold')
    
    # Add reference lines for key latitudes
    ax.axvline(x=0, color='red', linewidth=2, alpha=0.5, linestyle='-', label='Equator')
    ax.axvline(x=66.5, color='lightblue', linewidth=1.5, alpha=0.5, linestyle='--', label='Arctic Circle')
    ax.axvline(x=-66.5, color='lightblue', linewidth=1.5, alpha=0.5, linestyle='--', label='Antarctic Circle')
    ax.axvline(x=23.5, color='orange', linewidth=1.5, alpha=0.5, linestyle='--', label='Tropic of Cancer')
    ax.axvline(x=-23.5, color='orange', linewidth=1.5, alpha=0.5, linestyle='--', label='Tropic of Capricorn')
    
    # Configure axes
    ax.set_xlabel('Latitude (degrees)', fontsize=14, fontweight='bold')
    ax.set_ylabel('Number of Image Captures', fontsize=14, fontweight='bold')
    ax.set_xlim(-90, 90)
    ax.grid(True, alpha=0.3, axis='y')
    ax.set_axisbelow(True)
    
    # Add legend
    ax.legend(loc='upper right', fontsize=10)
    
    # Statistics
    total_captures = len(lats)
    mean_lat = np.mean(lats)
    std_lat = np.std(lats)
    
    # Title
    title = f'Geographic Distribution by Latitude - {strategy.upper()} Strategy\n'
    title += f'{total_captures:,} Total Captures | Mean: {mean_lat:.1f}° | Std: {std_lat:.1f}°'
    ax.set_title(title, fontsize=16, fontweight='bold', pad=20)
    
    # Add statistics box
    # Calculate captures by zone
    tropical = np.sum((lats >= -23.5) & (lats <= 23.5))
    northern_temperate = np.sum((lats > 23.5) & (lats < 66.5))
    southern_temperate = np.sum((lats > -66.5) & (lats < -23.5))
    arctic = np.sum(lats >= 66.5)
    antarctic = np.sum(lats <= -66.5)
    
    stats_text = 'Captures by Zone:\n'
    stats_text += f'  Arctic (≥66.5°N):      {arctic:8,} ({100*arctic/total_captures:5.1f}%)\n'
    stats_text += f'  N. Temperate:          {northern_temperate:8,} ({100*northern_temperate/total_captures:5.1f}%)\n'
    stats_text += f'  Tropical (±23.5°):     {tropical:8,} ({100*tropical/total_captures:5.1f}%)\n'
    stats_text += f'  S. Temperate:          {southern_temperate:8,} ({100*southern_temperate/total_captures:5.1f}%)\n'
    stats_text += f'  Antarctic (≤-66.5°S):  {antarctic:8,} ({100*antarctic/total_captures:5.1f}%)'
    
    ax.text(0.02, 0.98, stats_text, transform=ax.transAxes,
            fontsize=10, verticalalignment='top', family='monospace',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.9))
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()

def create_world_map_with_captures(lats, lons, strategy, sat_count, output_path):
    """Create a world map showing capture locations with basemap and heatmap overlay."""
    
    fig, ax = plt.subplots(figsize=(20, 10))
    
    # Draw simplified world map FIRST (as background)
    # Coastlines - very simplified continents
    # We'll draw these as filled patches so they show behind the heatmap
    from matplotlib.patches import Polygon
    
    # Light gray land masses (simplified shapes)
    land_color = '#E8E8E8'
    ocean_color = '#D0E8F0'
    
    # Fill ocean background
    ax.add_patch(plt.Rectangle((-180, -90), 360, 180, fill=True, 
                                facecolor=ocean_color, edgecolor='none', zorder=0))
    
    # Simplified continent polygons (very rough approximations)
    # North America
    north_america = [(-170, 15), (-170, 72), (-50, 72), (-50, 15), (-80, 8), 
                     (-90, 15), (-100, 30), (-130, 50), (-160, 60), (-170, 50)]
    ax.add_patch(Polygon(north_america, facecolor=land_color, edgecolor='darkgray', 
                         linewidth=0.5, zorder=1, alpha=0.7))
    
    # South America
    south_america = [(-80, 12), (-35, -10), (-35, -55), (-70, -55), (-80, -30)]
    ax.add_patch(Polygon(south_america, facecolor=land_color, edgecolor='darkgray', 
                         linewidth=0.5, zorder=1, alpha=0.7))
    
    # Europe
    europe = [(-10, 35), (40, 35), (40, 71), (-10, 60)]
    ax.add_patch(Polygon(europe, facecolor=land_color, edgecolor='darkgray', 
                         linewidth=0.5, zorder=1, alpha=0.7))
    
    # Africa
    africa = [(-20, 37), (50, 37), (50, -35), (25, -35), (-20, 20)]
    ax.add_patch(Polygon(africa, facecolor=land_color, edgecolor='darkgray', 
                         linewidth=0.5, zorder=1, alpha=0.7))
    
    # Asia
    asia = [(30, 10), (150, 10), (150, 75), (30, 75), (30, 40)]
    ax.add_patch(Polygon(asia, facecolor=land_color, edgecolor='darkgray', 
                         linewidth=0.5, zorder=1, alpha=0.7))
    
    # Australia
    australia = [(113, -10), (153, -10), (153, -43), (113, -43)]
    ax.add_patch(Polygon(australia, facecolor=land_color, edgecolor='darkgray', 
                         linewidth=0.5, zorder=1, alpha=0.7))
    
    # Create 2D histogram heatmap (OVER the map background)
    lon_bins = np.linspace(-180, 180, 180)  # 2 degree resolution
    lat_bins = np.linspace(-90, 90, 90)     # 2 degree resolution
    
    # Create the heatmap with transparency so land shows through
    counts, xedges, yedges, im = ax.hist2d(
        lons, lats,
        bins=[lon_bins, lat_bins],
        cmap='hot',
        cmin=1,  # Don't show zero counts
        alpha=0.75,  # Semi-transparent so we can see land underneath
        zorder=2  # Draw on top of land
    )
    
    # Add colorbar
    cbar = plt.colorbar(im, ax=ax, pad=0.02)
    cbar.set_label('Image Captures per Grid Cell', rotation=270, labelpad=25, fontsize=14, fontweight='bold')
    
    # Draw key latitude/longitude lines (overlaid on heatmap)
    ax.axhline(y=0, color='blue', linewidth=2, alpha=0.8, linestyle='-', label='Equator', zorder=3)
    ax.axvline(x=0, color='blue', linewidth=2, alpha=0.8, linestyle='-', label='Prime Meridian', zorder=3)
    
    # Polar circles
    ax.axhline(y=66.5, color='cyan', linewidth=1.5, alpha=0.7, linestyle='--', label='Arctic Circle', zorder=3)
    ax.axhline(y=-66.5, color='cyan', linewidth=1.5, alpha=0.7, linestyle='--', label='Antarctic Circle', zorder=3)
    
    # Tropics
    ax.axhline(y=23.5, color='orange', linewidth=1.5, alpha=0.7, linestyle='--', label='Tropic of Cancer', zorder=3)
    ax.axhline(y=-23.5, color='orange', linewidth=1.5, alpha=0.7, linestyle='--', label='Tropic of Capricorn', zorder=3)
    
    # Add longitude grid every 30 degrees
    for lon in range(-180, 181, 30):
        ax.axvline(x=lon, color='gray', linewidth=0.5, alpha=0.2, linestyle=':')
    
    # Add latitude grid every 15 degrees
    for lat in range(-90, 91, 15):
        ax.axhline(y=lat, color='gray', linewidth=0.5, alpha=0.2, linestyle=':')
    
    # Configure axes
    ax.set_xlabel('Longitude (degrees)', fontsize=14, fontweight='bold')
    ax.set_ylabel('Latitude (degrees)', fontsize=14, fontweight='bold')
    ax.set_xlim(-180, 180)
    ax.set_ylim(-90, 90)
    ax.set_aspect('equal')
    
    # Grid
    ax.grid(True, alpha=0.2, linestyle=':', linewidth=0.5)
    ax.set_axisbelow(True)
    
    # Title
    total_captures = len(lats)
    title = f'World Map - Image Capture Distribution\n'
    title += f'{strategy.upper()} Strategy | {sat_count} Satellites\n'
    title += f'{total_captures:,} Total Captures (aggregated across 4 image sizes)'
    ax.set_title(title, fontsize=16, fontweight='bold', pad=20)
    
    # Legend
    handles, labels = ax.get_legend_handles_labels()
    # Remove duplicate labels
    by_label = dict(zip(labels, handles))
    ax.legend(by_label.values(), by_label.keys(), loc='lower left', fontsize=10)
    
    # Add coverage statistics
    lat_coverage = lats.max() - lats.min()
    lon_coverage = lons.max() - lons.min()
    
    stats_text = f'Coverage:\n'
    stats_text += f'  Latitude:  {lats.min():.1f}° to {lats.max():.1f}° ({lat_coverage:.1f}° span)\n'
    stats_text += f'  Longitude: {lons.min():.1f}° to {lons.max():.1f}° ({lon_coverage:.1f}° span)'
    
    ax.text(0.02, 0.98, stats_text, transform=ax.transAxes,
            fontsize=11, verticalalignment='top',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.9))
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()

def main():
    print("=" * 88)
    print(" " * 15 + "GEOGRAPHIC CAPTURE DISTRIBUTION BY STRATEGY")
    print("=" * 88)
    print()
    
    # Create output directory
    output_dir = Path('comparison_charts')
    output_dir.mkdir(exist_ok=True)
    
    # Scan all configurations
    print("Scanning configurations...")
    configs = scan_all_configurations()
    print(f"Found {len(configs)} configurations\n")
    
    strategies = ['close-spaced', 'orbit-spaced', 'frame-spaced', 'close-orbit-spaced']
    sat_counts = [1, 50, 100, 200]
    
    print("Aggregating capture locations by strategy and constellation size...")
    print("(Triggers are independent of policy and image size)\n")
    
    for strategy in strategies:
        print(f"📍 Processing {strategy}...")
        
        for sat_count in sat_counts:
            # Load all captures for this strategy and constellation size
            lats, lons = load_all_captures_for_strategy(configs, strategy, sat_count)
            
            if len(lats) == 0:
                print(f"  ⚠️  No data found for {strategy} with {sat_count} satellites")
                continue
            
            print(f"  {sat_count:3d} sats: {len(lats):7,} captures", end='')
            
            # Generate latitude histogram
            hist_output = output_dir / f'geo_latitude_histogram_{strategy}_{sat_count}sats.png'
            create_latitude_histogram(lats, strategy, hist_output)
            
            # Generate world map
            map_output = output_dir / f'geo_world_map_{strategy}_{sat_count}sats.png'
            create_world_map_with_captures(lats, lons, strategy, sat_count, map_output)
            print(f" → Histogram + Map saved")
        
        print()
    
    print("=" * 88)
    print(" " * 30 + "✅ ANALYSIS COMPLETE!")
    print("=" * 88)
    print()
    print("Generated outputs:")
    print("  • 16 latitude histograms (4 strategies × 4 constellation sizes)")
    print("  • 16 world maps (4 strategies × 4 constellation sizes)")

if __name__ == '__main__':
    main()
