#!/usr/bin/env python3
"""
Debug Buffer Visualization - Visual FIFO Queue Analysis
========================================================
Creates a visual chart showing:
1. Earth map with color-coded image capture locations
2. Buffer state timeline showing what's in queue
3. Download events showing which images drain
"""

import zipfile
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib import image as mpimg
from collections import deque
from pathlib import Path

def debug_buffer_visualization():
    """
    Create visual debug chart showing buffer state and geographic locations.
    """
    
    # Use a small configuration for debugging (1 satellite)
    config_path = Path('constellation_analysis_20251016_223851_02799_01/close-spaced/simulation_logs.zip')
    
    if not config_path.exists():
        print(f"❌ Config not found: {config_path}")
        return
    
    print("=" * 80)
    print("Creating Visual Buffer Debug Chart...")
    print("=" * 80)
    
    # Load data
    with zipfile.ZipFile(config_path) as z:
        with z.open('sticky/visibility_log.csv') as f:
            df = pd.read_csv(f)
    
    # Find rows with downloads
    download_rows = df[df['downloaded_mb'] > 0]
    if len(download_rows) > 0:
        first_download_idx = download_rows.index[0]
        start_idx = max(0, first_download_idx - 10)
        end_idx = min(len(df), first_download_idx + 30)
        df = df.iloc[start_idx:end_idx]
    else:
        df = df.head(100)
    
    # Image size from config
    image_size_mb = 2.799
    
    # Track all images and their status
    all_images = []  # List of all images ever captured
    sat_buffer = deque()  # Current buffer state
    
    # Colors for up to 20 images
    colors = plt.cm.tab20(np.linspace(0, 1, 20))
    
    # Process events and track images
    images_captured = 0
    
    for idx, row in df.iterrows():
        sat_id = row['sat_id']
        time = row['time']
        image_taken = row['image_taken']
        downloaded_mb = row['downloaded_mb']
        
        # Capture event
        if image_taken == 1:
            images_captured += 1
            lat = row['lat_deg']
            lon = ((row['lon_deg'] + 180) % 360) - 180
            
            image_info = {
                'id': images_captured,
                'lat': lat,
                'lon': lon,
                'size_mb': image_size_mb,
                'remaining_mb': image_size_mb,
                'color': colors[(images_captured - 1) % 20],
                'capture_time': time,
                'download_time': None,
                'status': 'buffered'
            }
            sat_buffer.append(image_info)
            all_images.append(image_info)
        
        # Download event
        if downloaded_mb > 0:
            remaining_to_drain = downloaded_mb
            
            while remaining_to_drain > 0.0001 and len(sat_buffer) > 0:
                oldest_image = sat_buffer[0]
                
                if oldest_image['remaining_mb'] <= remaining_to_drain + 0.0001:
                    # Fully downloaded
                    oldest_image['download_time'] = time
                    oldest_image['status'] = 'downloaded'
                    remaining_to_drain -= oldest_image['remaining_mb']
                    sat_buffer.popleft()
                else:
                    # Partially downloaded
                    oldest_image['remaining_mb'] -= remaining_to_drain
                    remaining_to_drain = 0
        
        # Stop after we have enough images
        if images_captured >= 20:
            break
    
    # Create the visualization
    fig = plt.figure(figsize=(20, 12))
    gs = fig.add_gridspec(3, 2, height_ratios=[2, 1, 1], hspace=0.3, wspace=0.3)
    
    # ============================================================================
    # TOP: Earth map with color-coded image locations
    # ============================================================================
    ax_map = fig.add_subplot(gs[0, :])
    
    # Load and display real Earth image as background
    earth_img_path = Path('earth_map.jpg')
    if earth_img_path.exists():
        try:
            earth_img = mpimg.imread(earth_img_path)
            # Display Earth image with proper extent (lon: -180 to 180, lat: -90 to 90)
            ax_map.imshow(earth_img, extent=[-180, 180, -90, 90], aspect='auto', alpha=0.6)
        except Exception as e:
            print(f"Warning: Could not load Earth image: {e}")
            # Fallback: light blue ocean background
            ax_map.set_facecolor('#d4e6f1')
    else:
        print(f"Warning: Earth image not found at {earth_img_path}")
        ax_map.set_facecolor('#d4e6f1')
    
    # Plot lat/lon reference grid
    for lat in range(-90, 91, 30):
        ax_map.axhline(y=lat, color='white', linestyle='--', linewidth=0.5, alpha=0.7)
    for lon in range(-180, 181, 30):
        ax_map.axvline(x=lon, color='white', linestyle='--', linewidth=0.5, alpha=0.7)
    
    # Plot each image with its color (matching legend style)
    for img in all_images[:20]:
        marker = 'o'
        size = 400
        
        # Plot the colored circle with minimal white outline
        ax_map.scatter(img['lon'], img['lat'], 
                      c=[img['color']], 
                      s=size,
                      marker=marker,
                      edgecolors='black',
                      linewidths=1.0,
                      alpha=0.95,
                      zorder=10)
    
    ax_map.set_xlim(-180, 180)
    ax_map.set_ylim(-90, 90)
    ax_map.set_xlabel('Longitude (degrees)', fontsize=12, fontweight='bold', color='white')
    ax_map.set_ylabel('Latitude (degrees)', fontsize=12, fontweight='bold', color='white')
    ax_map.grid(True, alpha=0.3, color='white')
    ax_map.set_aspect('equal')
    
    # Style the tick labels for better visibility
    ax_map.tick_params(colors='white', labelsize=10)
    for spine in ax_map.spines.values():
        spine.set_edgecolor('white')
        spine.set_linewidth(2)
    
    # ============================================================================
    # MIDDLE LEFT: Legend with image details
    # ============================================================================
    ax_legend = fig.add_subplot(gs[1, 0])
    ax_legend.axis('off')
    
    legend_text = "IMAGE LEGEND\n" + "=" * 50 + "\n\n"
    for img in all_images[:20]:
        status_symbol = "⚫" if img['status'] == 'downloaded' else "⬛"
        legend_text += f"{status_symbol} Image #{img['id']:2d}: "
        legend_text += f"({img['lat']:6.2f}°, {img['lon']:7.2f}°)  "
        legend_text += f"Captured: t={img['capture_time']:.0f}s"
        if img['download_time']:
            legend_text += f"  Downloaded: t={img['download_time']:.0f}s"
        legend_text += "\n"
    
    ax_legend.text(0.05, 0.95, legend_text, 
                  fontsize=9, family='monospace',
                  verticalalignment='top',
                  transform=ax_legend.transAxes)
    
    # Add color patches for each image
    y_start = 0.95
    for i, img in enumerate(all_images[:20]):
        y_pos = y_start - (i * 0.045)
        rect = mpatches.Rectangle((0.0, y_pos - 0.02), 0.03, 0.03, 
                                  facecolor=img['color'], 
                                  edgecolor='black',
                                  transform=ax_legend.transAxes)
        ax_legend.add_patch(rect)
    
    # ============================================================================
    # MIDDLE RIGHT: Buffer state summary
    # ============================================================================
    ax_buffer = fig.add_subplot(gs[1, 1])
    ax_buffer.axis('off')
    
    buffer_text = "BUFFER STATE SUMMARY\n" + "=" * 50 + "\n\n"
    buffer_text += f"Total images captured: {len(all_images)}\n"
    buffer_text += f"Images downloaded: {sum(1 for img in all_images if img['status'] == 'downloaded')}\n"
    buffer_text += f"Images still buffered: {sum(1 for img in all_images if img['status'] == 'buffered')}\n\n"
    
    buffer_text += "FIFO QUEUE EXPLANATION:\n"
    buffer_text += "• Images are added to BACK of queue (when captured)\n"
    buffer_text += "• Downloads drain from FRONT of queue (oldest first)\n"
    buffer_text += "• Color-coded circles show WHERE images were captured\n"
    buffer_text += "• ⚫ circles = downloaded and plotted\n"
    buffer_text += "• ⬛ squares = still in buffer (not downloaded yet)\n"
    
    ax_buffer.text(0.05, 0.95, buffer_text, 
                  fontsize=10,
                  verticalalignment='top',
                  transform=ax_buffer.transAxes)
    
    # ============================================================================
    # BOTTOM: Timeline showing buffer state over time
    # ============================================================================
    ax_timeline = fig.add_subplot(gs[2, :])
    
    # For each image, show when it was captured and downloaded
    for img in all_images[:20]:
        capture_t = img['capture_time']
        download_t = img['download_time'] if img['download_time'] else capture_t + 100
        
        # Draw line from capture to download
        ax_timeline.plot([capture_t, download_t], [img['id'], img['id']], 
                        color=img['color'], linewidth=4, alpha=0.7)
        
        # Capture marker
        ax_timeline.scatter([capture_t], [img['id']], 
                          c=[img['color']], s=100, marker='s', 
                          edgecolors='black', linewidths=1, zorder=5)
        
        # Download marker (if downloaded)
        if img['download_time']:
            ax_timeline.scatter([download_t], [img['id']], 
                              c=[img['color']], s=100, marker='o', 
                              edgecolors='black', linewidths=1, zorder=5)
    
    ax_timeline.set_xlabel('Time (seconds)', fontsize=12, fontweight='bold')
    ax_timeline.set_ylabel('Image ID', fontsize=12, fontweight='bold')
    ax_timeline.set_title('BUFFER TIMELINE (⬛ = Capture, ⚫ = Download)', 
                         fontsize=12, fontweight='bold')
    ax_timeline.grid(True, alpha=0.3)
    ax_timeline.set_ylim(0.5, min(21, len(all_images) + 0.5))
    
    # Overall title
    fig.suptitle('FIFO BUFFER SIMULATION DEBUG - Visual Analysis\n' + 
                'Config: close-spaced, 2.799mb, 1sat, policy=sticky', 
                fontsize=16, fontweight='bold', y=0.98)
    
    # Save
    output_path = Path('debug_buffer_visual.png')
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"✅ Saved: {output_path}")
    plt.close()
    
    # Print summary
    print()
    print("=" * 80)
    print("CHART CONTENTS:")
    print("=" * 80)
    print("TOP:    Earth map with color-coded image locations")
    print("        • Each color = one image")
    print("        • ⚫ circles = downloaded images")
    print("        • ⬛ squares = still in buffer")
    print()
    print("MIDDLE: Legend showing:")
    print("        • Image ID, location (lat, lon)")
    print("        • Capture time and download time")
    print("        • Color patch matching map")
    print()
    print("BOTTOM: Timeline showing buffer life:")
    print("        • ⬛ = when image captured")
    print("        • ⚫ = when image downloaded")
    print("        • Line = time spent in buffer")
    print("=" * 80)

if __name__ == '__main__':
    debug_buffer_visualization()
