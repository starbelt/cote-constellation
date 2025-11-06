#!/usr/bin/env python3
"""
Geographic Capture Distribution - Combined Strategy View
=========================================================
Creates one comprehensive chart per spacing strategy showing:
- Top row: 4 world map heatmaps (one per constellation size)
- Bottom row: 4 latitude histograms (one per constellation size)

This allows easy comparison of how capture distribution changes with constellation size.
"""

import zipfile
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import image as mpimg
from pathlib import Path
import re

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

def load_all_captures_for_strategy(configs, strategy, sat_count):
    """Load ALL capture locations for a given strategy and constellation size."""
    all_lats = []
    all_lons = []
    
    for config in configs:
        if config['sat_count'] != sat_count:
            continue
            
        strategy_dir = config['folder'] / strategy
        zip_path = strategy_dir / 'simulation_logs.zip'
        
        if not zip_path.exists():
            continue
        
        try:
            with zipfile.ZipFile(zip_path) as z:
                csv_name = 'sticky/visibility_log.csv'
                with z.open(csv_name) as f:
                    df = pd.read_csv(f)
                    captures = df[df['image_taken'] == 1].copy()
                    
                    if len(captures) > 0:
                        lats = captures['lat_deg'].values
                        lons = captures['lon_deg'].values
                        lons = ((lons + 180) % 360) - 180
                        all_lats.extend(lats)
                        all_lons.extend(lons)
                        
        except Exception as e:
            print(f"⚠️  Warning: Could not read {strategy} from {config['folder'].name}: {e}")
            continue
    
    return np.array(all_lats), np.array(all_lons)

def add_world_map_background(ax):
    """Add NASA Blue Marble Earth image as background."""
    earth_img_path = Path('earth_map.jpg')
    
    if earth_img_path.exists():
        try:
            earth_img = mpimg.imread(earth_img_path)
            # Display Earth image with proper extent (lon: -180 to 180, lat: -90 to 90)
            ax.imshow(earth_img, extent=[-180, 180, -90, 90], aspect='auto', alpha=0.5, zorder=0)
        except Exception as e:
            print(f"⚠️  Warning: Could not load Earth image: {e}")
            # Fallback: soft blue ocean background
            ax.set_facecolor('#A8C5DD')
    else:
        print(f"⚠️  Warning: Earth image not found at {earth_img_path}")
        # Fallback: soft blue ocean background
        ax.set_facecolor('#A8C5DD')

def create_combined_strategy_chart(configs, strategy, output_path):
    """Create one chart with 8 subplots: 4 maps + 4 histograms for one strategy."""
    
    sat_counts = [1, 50, 100, 200]
    
    # Create LARGER figure with 2 rows × 4 columns (increased size for better visibility)
    fig = plt.figure(figsize=(40, 18))  # Increased from 36x16 to 40x18 for better heatmap visibility
    gs = fig.add_gridspec(2, 4, hspace=0.35, wspace=0.25, 
                          top=0.92, bottom=0.08, left=0.05, right=0.98)
    
    # Find global max for consistent color scale across all maps
    global_max_map = 0
    global_max_hist = 0
    all_data = {}
    
    # Load all data first
    for sat_count in sat_counts:
        lats, lons = load_all_captures_for_strategy(configs, strategy, sat_count)
        all_data[sat_count] = (lats, lons)
        
        if len(lats) > 0:
            # For map colorbar
            lon_bins = np.linspace(-180, 180, 180)
            lat_bins = np.linspace(-90, 90, 90)
            counts_2d, _, _ = np.histogram2d(lons, lats, bins=[lon_bins, lat_bins])
            global_max_map = max(global_max_map, counts_2d.max())
            
            # For histogram
            lat_bins_hist = np.arange(-90, 95, 5)
            counts_hist, _ = np.histogram(lats, bins=lat_bins_hist)
            global_max_hist = max(global_max_hist, counts_hist.max())
    
    # ==================== TOP ROW: WORLD MAPS ====================
    for i, sat_count in enumerate(sat_counts):
        ax = fig.add_subplot(gs[0, i])
        lats, lons = all_data[sat_count]
        
        if len(lats) == 0:
            ax.text(0.5, 0.5, 'No Data', ha='center', va='center',
                   transform=ax.transAxes, fontsize=14)
            ax.set_xlim(-180, 180)
            ax.set_ylim(-90, 90)
            continue
        
        # Add world map background
        add_world_map_background(ax)
        
        # Create heatmap
        lon_bins = np.linspace(-180, 180, 180)
        lat_bins = np.linspace(-90, 90, 90)
        _, _, _, im = ax.hist2d(lons, lats, bins=[lon_bins, lat_bins],
                                cmap='hot', cmin=1, vmax=global_max_map,
                                alpha=0.75, zorder=2)
        
        # Add reference lines
        ax.axhline(y=0, color='blue', linewidth=1.5, alpha=0.7, linestyle='-', zorder=3)
        ax.axvline(x=0, color='blue', linewidth=1.5, alpha=0.7, linestyle='-', zorder=3)
        ax.axhline(y=66.5, color='cyan', linewidth=1, alpha=0.6, linestyle='--', zorder=3)
        ax.axhline(y=-66.5, color='cyan', linewidth=1, alpha=0.6, linestyle='--', zorder=3)
        ax.axhline(y=23.5, color='orange', linewidth=1, alpha=0.6, linestyle='--', zorder=3)
        ax.axhline(y=-23.5, color='orange', linewidth=1, alpha=0.6, linestyle='--', zorder=3)
        
        # Grid
        for lon in range(-180, 181, 30):
            ax.axvline(x=lon, color='gray', linewidth=0.3, alpha=0.2, linestyle=':')
        for lat in range(-90, 91, 15):
            ax.axhline(y=lat, color='gray', linewidth=0.3, alpha=0.2, linestyle=':')
        
        # Configure axes
        ax.set_xlim(-180, 180)
        ax.set_ylim(-90, 90)
        ax.set_aspect('equal')
        ax.set_xlabel('Longitude (°)', fontsize=12, fontweight='bold')
        ax.set_ylabel('Latitude (°)', fontsize=12, fontweight='bold')
        ax.tick_params(labelsize=10)
        
        # Title
        ax.set_title(f'{sat_count} Satellites\n{len(lats):,} captures', 
                    fontsize=13, fontweight='bold', pad=10)
        
        # Add colorbar to rightmost map
        if i == 3:
            cbar = plt.colorbar(im, ax=ax, pad=0.02, fraction=0.046)
            cbar.set_label('Captures/Grid Cell', rotation=270, labelpad=18, 
                          fontsize=11, fontweight='bold')
            cbar.ax.tick_params(labelsize=10)
    
    # ==================== BOTTOM ROW: LATITUDE HISTOGRAMS ====================
    for i, sat_count in enumerate(sat_counts):
        ax = fig.add_subplot(gs[1, i])
        lats, _ = all_data[sat_count]
        
        if len(lats) == 0:
            ax.text(0.5, 0.5, 'No Data', ha='center', va='center',
                   transform=ax.transAxes, fontsize=14)
            ax.set_xlim(-90, 90)
            continue
        
        # Create histogram
        lat_bins = np.arange(-90, 95, 5)
        counts, edges, patches = ax.hist(lats, bins=lat_bins, color='steelblue',
                                         edgecolor='black', linewidth=0.5, alpha=0.8)
        
        # Add reference lines
        ax.axvline(x=0, color='red', linewidth=1.5, alpha=0.6, linestyle='-', zorder=0)
        ax.axvline(x=66.5, color='cyan', linewidth=1, alpha=0.5, linestyle='--', zorder=0)
        ax.axvline(x=-66.5, color='cyan', linewidth=1, alpha=0.5, linestyle='--', zorder=0)
        ax.axvline(x=23.5, color='orange', linewidth=1, alpha=0.5, linestyle='--', zorder=0)
        ax.axvline(x=-23.5, color='orange', linewidth=1, alpha=0.5, linestyle='--', zorder=0)
        
        # Configure axes
        ax.set_xlabel('Latitude (°)', fontsize=12, fontweight='bold')
        ax.set_ylabel('Captures', fontsize=12, fontweight='bold')
        ax.set_xlim(-90, 90)
        ax.set_ylim(0, global_max_hist * 1.05)
        ax.grid(True, alpha=0.3, axis='y')
        ax.set_axisbelow(True)
        ax.tick_params(labelsize=10)
        
        # Calculate zone statistics (compact format)
        tropical = np.sum((lats >= -23.5) & (lats <= 23.5))
        northern = np.sum((lats > 23.5) & (lats < 66.5))
        southern = np.sum((lats > -66.5) & (lats < -23.5))
        arctic = np.sum(lats >= 66.5)
        antarctic = np.sum(lats <= -66.5)
        total = len(lats)
        
        # Add compact stats box
        stats_text = f'Arctic: {100*arctic/total:.1f}%\n'
        stats_text += f'N.Temp: {100*northern/total:.1f}%\n'
        stats_text += f'Tropic: {100*tropical/total:.1f}%\n'
        stats_text += f'S.Temp: {100*southern/total:.1f}%\n'
        stats_text += f'Antarc: {100*antarctic/total:.1f}%'
        
        ax.text(0.98, 0.97, stats_text, transform=ax.transAxes,
                fontsize=9, verticalalignment='top', horizontalalignment='right',
                family='monospace',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8, pad=0.4))
    
    # Main title
    fig.suptitle(f'Geographic Capture Distribution - {strategy.upper()} Strategy\n' +
                 'Top: World Map Heatmaps | Bottom: Latitude Histograms | ' +
                 'Each aggregated across 4 image sizes',
                 fontsize=18, fontweight='bold', y=0.97)
    
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    
    print(f"  ✅ Combined chart → {output_path.name}")

def main():
    print("=" * 88)
    print(" " * 10 + "GEOGRAPHIC CAPTURE DISTRIBUTION - COMBINED STRATEGY VIEWS")
    print("=" * 88)
    print()
    
    # Create output directory
    output_dir = Path('constellation_analysis') / 'comparison_charts'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Scan all configurations
    print("Scanning configurations...")
    configs = scan_all_configurations()
    print(f"Found {len(configs)} configurations\n")
    
    strategies = ['close-spaced', 'orbit-spaced', 'frame-spaced', 'close-orbit-spaced']
    
    print("Generating combined charts (one per strategy)...")
    print("Each chart shows 4 constellation sizes with maps + histograms\n")
    
    for strategy in strategies:
        print(f"📍 Processing {strategy}...")
        output_path = output_dir / f'geo_combined_{strategy}.png'
        create_combined_strategy_chart(configs, strategy, output_path)
    
    print("\n" + "=" * 88)
    print(" " * 30 + "✅ ANALYSIS COMPLETE!")
    print("=" * 88)
    print()
    print("Generated outputs:")
    print("  • 4 combined charts (one per spacing strategy)")
    print("  • Each chart contains:")
    print("    - 4 world map heatmaps (top row)")
    print("    - 4 latitude histograms (bottom row)")
    print("    - Covers constellation sizes: 1, 50, 100, 200 satellites")

if __name__ == '__main__':
    main()
