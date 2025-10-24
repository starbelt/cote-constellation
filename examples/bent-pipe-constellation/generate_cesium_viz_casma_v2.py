#!/usr/bin/env python3
"""
Generate Cesium CZML visualization files for constellation analysis.
Follows CASMA Cesium demonstration methodology.

KEY VISUALIZATION FEATURES:
- All satellites GREY by default
- Satellite turns GREEN + shows connection line ONLY when connected=1
- Dynamic label showing satellite ID and data rate when connected
- Full 1-second time resolution (NO sampling)
- Svalbard ground station at correct coordinates
- Support for multiple spacing strategies, policies, and image sizes
"""

import pandas as pd
import json
from datetime import datetime, timedelta
from pathlib import Path

# Configuration options
CONSTELLATION_SIZES = [1, 50, 100, 200]
SPACING_STRATEGIES = ['orbit-spaced', 'close-orbit-spaced', 'close-spaced', 'frame-spaced']
LINK_POLICIES = ['sticky', 'fifo', 'random', 'roundrobin']
IMAGE_SIZES = ['00027', '00279', '02799', '28000']  # MB

# Start time for the visualization (arbitrary)
start_time = datetime(2025, 1, 1, 0, 0, 0)

# Svalbard ground station coordinates (from gnd-0000000000.dat)
GS_LAT = 78.2308
GS_LON = 15.3906
GS_ALT = 72.0  # meters HAE

# Colors
GREY = [128, 128, 128, 255]      # Default satellite color
GREEN = [0, 255, 0, 255]         # Connected satellite color
YELLOW = [255, 255, 0, 255]      # Ground station color

def generate_czml(num_sats, analysis_dir, spacing_strategy, link_policy):
    """Generate CZML file for a specific constellation configuration."""
    
    print(f"\nGenerating CZML for {num_sats} sats, {spacing_strategy}, {link_policy}...")
    
    # Load the visibility log from the analysis directory
    log_file = Path(analysis_dir) / spacing_strategy / link_policy / 'visibility_log.csv'
    
    if not log_file.exists():
        print(f"❌ File not found: {log_file}")
        print(f"   Checking for zipped logs...")
        # Try to extract if zipped
        zip_file = Path(analysis_dir) / 'orbit-spaced' / 'simulation_logs.zip'
        if zip_file.exists():
            import zipfile
            with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                zip_ref.extractall(Path(analysis_dir) / 'orbit-spaced')
            print(f"   ✅ Extracted logs from {zip_file.name}")
            # Check again after extraction
            if not log_file.exists():
                raise FileNotFoundError(f"visibility_log.csv not found even after extraction")
        else:
            raise FileNotFoundError(f"Cannot find visibility_log.csv or simulation_logs.zip")
    
    df = pd.read_csv(log_file)
    
    # Limit to first 20 minutes (1200 seconds) - FULL RESOLUTION, NO SAMPLING
    df = df[df['time'] <= 1200]
    
    print(f"  Data points: {len(df)} rows")
    print(f"  Time range: {df['time'].min():.1f} - {df['time'].max():.1f} seconds")
    
    czml = []
    
    # Document header
    czml.append({
        "id": "document",
        "name": f"{spacing_strategy} - {link_policy} - {num_sats} satellites",
        "version": "1.0",
        "clock": {
            "interval": f"{start_time.isoformat()}Z/{(start_time + timedelta(seconds=df['time'].max())).isoformat()}Z",
            "currentTime": f"{start_time.isoformat()}Z",
            "multiplier": 60,  # Speed up time 60x
            "range": "LOOP_STOP",
            "step": "SYSTEM_CLOCK_MULTIPLIER"
        }
    })
    
    # Ground station (Svalbard)
    czml.append({
        "id": "ground_station",
        "name": "Svalbard Ground Station",
        "position": {
            "cartographicDegrees": [GS_LON, GS_LAT, GS_ALT]
        },
        "point": {
            "pixelSize": 15,
            "color": {"rgba": YELLOW},
            "outlineColor": {"rgba": [0, 0, 0, 255]},
            "outlineWidth": 2
        },
        "label": {
            "text": "Svalbard GS",
            "font": "14px sans-serif",
            "fillColor": {"rgba": [255, 255, 255, 255]},
            "outlineColor": {"rgba": [0, 0, 0, 255]},
            "outlineWidth": 2,
            "pixelOffset": {"cartesian2": [0, -25]},
            "showBackground": True,
            "backgroundColor": {"rgba": [26, 26, 26, 178]}
        }
    })
    
    # Add each satellite
    for sat_id in sorted(df['sat_id'].unique()):
        sat_df = df[df['sat_id'] == sat_id].sort_values('time')
        
        # Build time-varying position (FULL RESOLUTION - NO SAMPLING)
        positions = []
        for _, row in sat_df.iterrows():
            time_str = (start_time + timedelta(seconds=row['time'])).isoformat() + "Z"
            sat_alt = 550000  # 550 km altitude in meters
            
            positions.extend([
                time_str,
                row['lon_deg'],
                row['lat_deg'],
                sat_alt
            ])
        
        # Build time-varying COLOR intervals
        # Grey by default, GREEN only when connected=1
        color_intervals = []
        current_connected = False
        interval_start = None
        
        for idx, row in sat_df.iterrows():
            time_str = (start_time + timedelta(seconds=row['time'])).isoformat() + "Z"
            is_connected = row['connected'] == 1
            
            if is_connected and not current_connected:
                # Just connected - start GREEN interval
                interval_start = time_str
                current_connected = True
            elif not is_connected and current_connected:
                # Just disconnected - close GREEN interval
                if interval_start:
                    color_intervals.append({
                        "interval": f"{interval_start}/{time_str}",
                        "rgba": GREEN
                    })
                current_connected = False
                interval_start = None
        
        # Close interval if still connected at end
        if current_connected and interval_start:
            last_time = (start_time + timedelta(seconds=sat_df.iloc[-1]['time'])).isoformat() + "Z"
            color_intervals.append({
                "interval": f"{interval_start}/{last_time}",
                "rgba": GREEN
            })
        
        # If no color intervals, satellite is always grey - add default
        if not color_intervals:
            first_time = (start_time + timedelta(seconds=sat_df.iloc[0]['time'])).isoformat() + "Z"
            last_time = (start_time + timedelta(seconds=sat_df.iloc[-1]['time'])).isoformat() + "Z"
            color_intervals = [{
                "interval": f"{first_time}/{last_time}",
                "rgba": GREY
            }]
        else:
            # Add grey intervals for gaps
            # Start with grey if first connection isn't at start
            first_conn_start = color_intervals[0]["interval"].split("/")[0]
            first_time = (start_time + timedelta(seconds=sat_df.iloc[0]['time'])).isoformat() + "Z"
            if first_conn_start != first_time:
                color_intervals.insert(0, {
                    "interval": f"{first_time}/{first_conn_start}",
                    "rgba": GREY
                })
            
            # Add grey between connections
            for i in range(len(color_intervals) - 1):
                end_of_conn = color_intervals[i]["interval"].split("/")[1]
                start_of_next = color_intervals[i+1]["interval"].split("/")[0]
                if end_of_conn != start_of_next:
                    color_intervals.insert(i+1, {
                        "interval": f"{end_of_conn}/{start_of_next}",
                        "rgba": GREY
                    })
            
            # End with grey if last connection isn't at end
            last_conn_end = color_intervals[-1]["interval"].split("/")[1]
            last_time = (start_time + timedelta(seconds=sat_df.iloc[-1]['time'])).isoformat() + "Z"
            if last_conn_end != last_time:
                color_intervals.append({
                    "interval": f"{last_conn_end}/{last_time}",
                    "rgba": GREY
                })
        
        # Build show intervals for connection line
        # CRITICAL: Must explicitly set show=false when NOT connected
        # Otherwise CZML will keep showing the line after it should disappear
        polyline_show_intervals = []
        current_connected = False
        interval_start = None
        
        for idx, row in sat_df.iterrows():
            time_str = (start_time + timedelta(seconds=row['time'])).isoformat() + "Z"
            is_connected = row['connected'] == 1
            
            if is_connected and not current_connected:
                # Start showing line
                interval_start = time_str
                current_connected = True
            elif not is_connected and current_connected:
                # Stop showing line
                if interval_start:
                    polyline_show_intervals.append({
                        "interval": f"{interval_start}/{time_str}",
                        "boolean": True
                    })
                current_connected = False
                interval_start = None
        
        # Close final interval if still connected at end
        if current_connected and interval_start:
            last_time = (start_time + timedelta(seconds=sat_df.iloc[-1]['time'])).isoformat() + "Z"
            polyline_show_intervals.append({
                "interval": f"{interval_start}/{last_time}",
                "boolean": True
            })
        
        # Add explicit FALSE intervals between TRUE intervals to hide line
        if polyline_show_intervals:
            # Add false interval at start if needed
            first_true_start = polyline_show_intervals[0]["interval"].split("/")[0]
            first_time = (start_time + timedelta(seconds=sat_df.iloc[0]['time'])).isoformat() + "Z"
            
            # Build complete list with false intervals
            complete_intervals = []
            if first_true_start != first_time:
                complete_intervals.append({
                    "interval": f"{first_time}/{first_true_start}",
                    "boolean": False
                })
            
            # Add all true intervals with false intervals between them
            for i, true_interval in enumerate(polyline_show_intervals):
                complete_intervals.append(true_interval)
                
                # Add false interval until next true interval (or end)
                true_end = true_interval["interval"].split("/")[1]
                if i < len(polyline_show_intervals) - 1:
                    next_true_start = polyline_show_intervals[i + 1]["interval"].split("/")[0]
                    complete_intervals.append({
                        "interval": f"{true_end}/{next_true_start}",
                        "boolean": False
                    })
                else:
                    # Add false interval to end if needed
                    last_time = (start_time + timedelta(seconds=sat_df.iloc[-1]['time'])).isoformat() + "Z"
                    if true_end != last_time:
                        complete_intervals.append({
                            "interval": f"{true_end}/{last_time}",
                            "boolean": False
                        })
            
            polyline_show_intervals = complete_intervals
        
        # Build label text that shows when connected
        # Format: Multi-line label with sat ID, DL rate, buffer, elevation, distance
        # Optimize: only add intervals when connected (not every second)
        label_text_intervals = []
        current_connected = False
        current_label = ""
        interval_start = None
        
        for idx, row in sat_df.iterrows():
            time_str = (start_time + timedelta(seconds=row['time'])).isoformat() + "Z"
            is_connected = row['connected'] == 1
            
            if is_connected:
                # Build multi-line label with all info
                sat_num = int(sat_id) % 1000
                dl_rate = row['downloaded_mb'] if pd.notna(row['downloaded_mb']) else 0
                buffer = row['buffer_mb'] if pd.notna(row['buffer_mb']) else 0
                elev = row['elevation_deg'] if pd.notna(row['elevation_deg']) else 0
                dist = row['distance_km'] if pd.notna(row['distance_km']) else 0
                
                label_text = (
                    f"Sat {sat_num:03d}\\n"
                    f"DL: {dl_rate:.1f} MB/s\\n"
                    f"Buf: {buffer:.1f} MB\\n"
                    f"Elev: {elev:.1f}°\\n"
                    f"Dist: {dist:.0f} km"
                )
                
                if not current_connected:
                    # Just connected - start new interval
                    interval_start = time_str
                    current_label = label_text
                    current_connected = True
                # If already connected, label updates are handled by the interval
            else:
                if current_connected:
                    # Just disconnected - close interval with label
                    label_text_intervals.append({
                        "interval": f"{interval_start}/{time_str}",
                        "string": current_label
                    })
                    current_connected = False
                    interval_start = None
        
        # Close final interval if still connected
        if current_connected and interval_start:
            last_time = (start_time + timedelta(seconds=sat_df.iloc[-1]['time'])).isoformat() + "Z"
            label_text_intervals.append({
                "interval": f"{interval_start}/{last_time}",
                "string": current_label
            })
        
        # If no label intervals, satellite never connects - hide label always
        if not label_text_intervals:
            first_time = (start_time + timedelta(seconds=sat_df.iloc[0]['time'])).isoformat() + "Z"
            last_time = (start_time + timedelta(seconds=sat_df.iloc[-1]['time'])).isoformat() + "Z"
            label_text_intervals = [{
                "interval": f"{first_time}/{last_time}",
                "string": ""
            }]
        
        # Satellite entity
        czml.append({
            "id": f"sat_{int(sat_id)}",
            "name": f"Satellite {int(sat_id) % 100}",
            "position": {
                "cartographicDegrees": positions
            },
            "point": {
                "pixelSize": 8,
                "color": color_intervals  # Time-varying color!
            },
            "label": {
                "text": label_text_intervals,  # Time-varying text
                "font": "14px bold sans-serif",
                "fillColor": {"rgba": [255, 255, 255, 255]},
                "outlineColor": {"rgba": [0, 0, 0, 255]},
                "outlineWidth": 2,
                "pixelOffset": {"cartesian2": [0, -20]},
                "showBackground": True,
                "backgroundColor": {"rgba": [0, 128, 0, 200]},  # Green background when connected
                "horizontalOrigin": "CENTER",
                "verticalOrigin": "BOTTOM"
            },
            "path": {
                "show": True,
                "width": 1,
                "material": {
                    "solidColor": {
                        "color": {"rgba": [100, 100, 100, 100]}
                    }
                },
                "trailTime": 600,  # 10 minute trail
                "resolution": 120
            }
        })
        
        # Connection line (only visible when connected=1)
        if polyline_show_intervals:
            czml.append({
                "id": f"connection_{int(sat_id)}",
                "name": f"Connection to Sat {int(sat_id) % 100}",
                "polyline": {
                    "show": polyline_show_intervals,
                    "positions": {
                        "references": [
                            "ground_station#position",
                            f"sat_{int(sat_id)}#position"
                        ]
                    },
                    "material": {
                        "solidColor": {
                            "color": {"rgba": GREEN}
                        }
                    },
                    "width": 3
                }
            })
    
    # Write CZML file
    output_dir = Path('cesium_output')
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / f'{spacing_strategy}_{link_policy}_{num_sats}sats.czml'
    
    with open(output_file, 'w') as f:
        json.dump(czml, f, indent=2)
    
    file_size_mb = output_file.stat().st_size / (1024 * 1024)
    print(f"✅ Generated: {output_file.name}")
    print(f"   File size: {file_size_mb:.2f} MB")
    
    return output_file.name

def generate_enhanced_viewer(czml_files):
    """Generate enhanced HTML viewer with dropdowns for spacing/policy/size selection."""
    
    # Parse filenames to extract options
    configs = []
    for filename in czml_files:
        # Format: {spacing}_{policy}_{size}sats.czml
        # e.g., orbit-spaced_sticky_100sats.czml
        parts = filename.replace('.czml', '').split('_')
        if len(parts) >= 3:
            # Handle hyphenated spacing names (orbit-spaced, close-orbit-spaced)
            if len(parts) == 4:  # close-orbit-spaced_policy_size
                spacing = f"{parts[0]}-{parts[1]}"
                policy = parts[2]
                size = parts[3].replace('sats', '')
            elif len(parts) == 3:  # orbit-spaced_policy_size or spacing_policy_size
                if '-' in parts[0]:  # Already hyphenated
                    spacing = parts[0]
                    policy = parts[1]
                    size = parts[2].replace('sats', '')
                else:
                    spacing = parts[0]
                    policy = parts[1]
                    size = parts[2].replace('sats', '')
            else:
                continue
            
            configs.append({
                'spacing': spacing,
                'policy': policy,
                'size': size,
                'filename': filename
            })
    
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Constellation Visualization</title>
    <script src="https://cesium.com/downloads/cesiumjs/releases/1.133/Build/Cesium/Cesium.js"></script>
    <link href="https://cesium.com/downloads/cesiumjs/releases/1.133/Build/Cesium/Widgets/widgets.css" rel="stylesheet">
    <style>
        html, body, #cesiumContainer {{
            width: 100%;
            height: 100%;
            margin: 0;
            padding: 0;
            overflow: hidden;
        }}
        
        #controlPanel {{
            position: absolute;
            top: 10px;
            left: 10px;
            background: rgba(26, 26, 26, 0.95);
            padding: 15px;
            border-radius: 8px;
            color: white;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            z-index: 1000;
            min-width: 280px;
        }}
        
        #controlPanel h3 {{
            margin: 0 0 15px 0;
            font-size: 15px;
            border-bottom: 2px solid #00ff00;
            padding-bottom: 8px;
        }}
        
        .control-group {{
            margin-bottom: 15px;
        }}
        
        .control-group label {{
            display: block;
            margin-bottom: 8px;
            font-size: 12px;
            font-weight: bold;
            color: #00ff00;
        }}
        
        .button-row {{
            display: flex;
            gap: 5px;
            flex-wrap: wrap;
        }}
        
        .toggle-btn {{
            flex: 1;
            min-width: 60px;
            padding: 8px 12px;
            border: 1px solid #444;
            background: rgba(50, 50, 50, 0.8);
            color: #aaa;
            border-radius: 4px;
            cursor: pointer;
            font-size: 11px;
            text-align: center;
            transition: all 0.2s;
        }}
        
        .toggle-btn:hover {{
            background: rgba(70, 70, 70, 0.9);
            border-color: #666;
        }}
        
        .toggle-btn.active {{
            background: #00ff00;
            color: #000;
            border-color: #00ff00;
            font-weight: bold;
        }}
        
        #infoDisplay {{
            margin-top: 15px;
            padding: 10px;
            background: rgba(0, 128, 0, 0.2);
            border-radius: 4px;
            border: 1px solid #00ff00;
            font-size: 11px;
        }}
        
        #infoDisplay div {{
            margin: 4px 0;
        }}
        
        .label-text {{
            color: #aaa;
        }}
        
        .value-text {{
            color: white;
            font-weight: bold;
        }}
        
        #loadingIndicator {{
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: rgba(0, 0, 0, 0.8);
            padding: 20px 40px;
            border-radius: 8px;
            color: #00ff00;
            font-size: 16px;
            display: none;
            z-index: 2000;
        }}
    </style>
</head>
<body>
    <div id="cesiumContainer"></div>
    <div id="loadingIndicator">Loading...</div>
    
    <div id="controlPanel">
        <h3>🛰️ Constellation Viewer</h3>
        
        <div class="control-group">
            <label>Spacing Strategy:</label>
            <div class="button-row">
                <button class="toggle-btn" data-group="spacing" data-value="orbit-spaced">Orbit</button>
                <button class="toggle-btn" data-group="spacing" data-value="close-orbit-spaced">Close-Orbit</button>
                <button class="toggle-btn" data-group="spacing" data-value="close-spaced">Close</button>
                <button class="toggle-btn" data-group="spacing" data-value="frame-spaced">Frame</button>
            </div>
        </div>
        
        <div class="control-group">
            <label>Link Policy:</label>
            <div class="button-row">
                <button class="toggle-btn" data-group="policy" data-value="sticky">Sticky</button>
                <button class="toggle-btn" data-group="policy" data-value="fifo">FIFO</button>
                <button class="toggle-btn" data-group="policy" data-value="random">Random</button>
                <button class="toggle-btn" data-group="policy" data-value="roundrobin">RoundRobin</button>
            </div>
        </div>
        
        <div class="control-group">
            <label>Image Size:</label>
            <div class="button-row">
                <button class="toggle-btn" data-group="imagesize" data-value="00027">2.7 MB</button>
                <button class="toggle-btn active" data-group="imagesize" data-value="00279">27.9 MB</button>
                <button class="toggle-btn" data-group="imagesize" data-value="02799">279.9 MB</button>
                <button class="toggle-btn" data-group="imagesize" data-value="28000">2.8 GB</button>
            </div>
        </div>
        
        <div class="control-group">
            <label>Constellation Size:</label>
            <div class="button-row">
                <button class="toggle-btn" data-group="size" data-value="50">50</button>
                <button class="toggle-btn active" data-group="size" data-value="100">100</button>
                <button class="toggle-btn" data-group="size" data-value="200">200</button>
            </div>
        </div>
        
        <div id="infoDisplay">
            <div><span class="label-text">Config:</span> <span class="value-text" id="currentConfig">-</span></div>
            <div><span class="label-text">Ground Station:</span> <span class="value-text">Svalbard</span></div>
            <div><span class="label-text">Status:</span> <span class="value-text" id="status">Ready</span></div>
        </div>
    </div>
    
    <script type="module">
        // Initialize Cesium viewer
        Cesium.Ion.defaultAccessToken = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJqdGkiOiI5Y2U0ZTk2Yi1jZGFkLTRkZjctYjM2Yi0yMTRjYzVjMDgxNzEiLCJpZCI6MjU5LCJpYXQiOjE3MzI0NjI4NjB9.JbEv0T8kLqDpvpFQR3PqWpQSLpZkUZ4cLqDpvpFQR3Pq';
        
        const viewer = new Cesium.Viewer('cesiumContainer', {{
            baseLayerPicker: false,
            geocoder: false,
            homeButton: false,
            sceneModePicker: false,
            navigationHelpButton: false,
            animation: true,
            timeline: true,
            fullscreenButton: false
        }});
        
        // Enable terrain
        viewer.terrainProvider = await Cesium.createWorldTerrainAsync();
        
        // File mapping
        const czmlFiles = {json.dumps({f"{c['spacing']}_{c['policy']}_{c['size']}": c['filename'] for c in configs}, indent=12)};
        
        let currentDataSource = null;
        let currentSelection = {{
            spacing: 'orbit-spaced',
            policy: 'sticky',
            imagesize: '00279',
            size: '100'
        }};
        
        // Load CZML function
        async function loadCZML() {{
            const key = `${{currentSelection.spacing}}_${{currentSelection.policy}}_${{currentSelection.size}}`;
            const filename = czmlFiles[key];
            
            if (!filename) {{
                document.getElementById('status').textContent = 'Not Available';
                document.getElementById('status').style.color = '#ff6666';
                return;
            }}
            
            document.getElementById('loadingIndicator').style.display = 'block';
            document.getElementById('status').textContent = 'Loading...';
            document.getElementById('status').style.color = '#ffaa00';
            
            try {{
                // Remove existing data source
                if (currentDataSource) {{
                    viewer.dataSources.remove(currentDataSource);
                }}
                
                // Load new CZML
                currentDataSource = await Cesium.CzmlDataSource.load(filename);
                await viewer.dataSources.add(currentDataSource);
                
                // Fly to Svalbard ground station
                viewer.camera.flyTo({{
                    destination: Cesium.Cartesian3.fromDegrees({GS_LON}, {GS_LAT}, 2000000),
                    duration: 2.0
                }});
                
                // Update info display
                const spacingLabel = currentSelection.spacing.replace('-', ' ');
                document.getElementById('currentConfig').textContent = 
                    `${{spacingLabel}} | ${{currentSelection.policy}} | ${{currentSelection.size}} sats`;
                document.getElementById('status').textContent = 'Active';
                document.getElementById('status').style.color = '#00ff00';
                
            }} catch (error) {{
                console.error('Error loading CZML:', error);
                document.getElementById('status').textContent = 'Error';
                document.getElementById('status').style.color = '#ff0000';
            }} finally {{
                document.getElementById('loadingIndicator').style.display = 'none';
            }}
        }}
        
        // Toggle button functionality
        document.querySelectorAll('.toggle-btn').forEach(btn => {{
            btn.addEventListener('click', function() {{
                const group = this.dataset.group;
                const value = this.dataset.value;
                
                // Remove active from all buttons in this group
                document.querySelectorAll(`[data-group="${{group}}"]`).forEach(b => {{
                    b.classList.remove('active');
                }});
                
                // Set this button as active
                this.classList.add('active');
                
                // Update current selection
                currentSelection[group] = value;
                
                // Load new visualization (except for imagesize which needs regeneration)
                if (group !== 'imagesize') {{
                    loadCZML();
                }}
            }});
        }});
        
        // Set initial active buttons
        document.querySelector('[data-group="spacing"][data-value="orbit-spaced"]').classList.add('active');
        document.querySelector('[data-group="policy"][data-value="sticky"]').classList.add('active');
        
        // Load initial visualization
        loadCZML();
    </script>
</body>
</html>'''
    
    # Write HTML file
    output_file = Path('cesium_output/constellation_viewer.html')
    with open(output_file, 'w') as f:
        f.write(html)
    
    print(f"✅ Generated: {output_file}")
    return output_file

# Map analysis directories (image_size_satcount format)
analysis_dir_map = {
    ('00027', 1): 'constellation_analysis_20251022_170000_00027_01',
    ('00027', 50): 'constellation_analysis_20251022_170029_00027_50',
    ('00027', 100): 'constellation_analysis_20251022_171204_00027_100',
    ('00027', 200): 'constellation_analysis_20251022_173521_00027_200',
    ('00279', 1): 'constellation_analysis_20251022_182439_00279_01',
    ('00279', 50): 'constellation_analysis_20251022_182518_00279_50',
    ('00279', 100): 'constellation_analysis_20251022_183657_00279_100',
    ('00279', 200): 'constellation_analysis_20251022_190047_00279_200',
    ('02799', 1): 'constellation_analysis_20251022_195835_02799_01',
    ('02799', 50): 'constellation_analysis_20251022_195920_02799_50',
    ('02799', 100): 'constellation_analysis_20251022_201325_02799_100',
    ('02799', 200): 'constellation_analysis_20251022_203816_02799_200',
    ('28000', 1): 'constellation_analysis_20251022_212850_28000_01',
    ('28000', 50): 'constellation_analysis_20251022_212931_28000_50',
    ('28000', 100): 'constellation_analysis_20251022_214230_28000_100',
    ('28000', 200): 'constellation_analysis_20251022_220920_28000_200',
}

# Generate CZML files for all combinations
print("=" * 80)
print("GENERATING CESIUM VISUALIZATION FILES (CASMA Methodology)")
print("=" * 80)
print()
print("Configuration:")
print(f"  - Ground Station: Svalbard ({GS_LAT:.4f}°N, {GS_LON:.4f}°E)")
print(f"  - Time window: 0-1200 seconds (20 minutes)")
print(f"  - Resolution: Full 1-second data (NO sampling)")
print(f"  - Features: Dynamic labels, time-varying colors, connection lines")
print()

generated_files = []

# Generate ALL combinations for all image sizes
for image_size in IMAGE_SIZES:
    print(f"\n{'='*80}")
    print(f"IMAGE SIZE: {image_size} MB")
    print(f"{'='*80}")
    
    for size in CONSTELLATION_SIZES:
        analysis_dir = analysis_dir_map.get((image_size, size))
        if not analysis_dir or not Path(analysis_dir).exists():
            print(f"\n⚠️  Skipping {size} sats - directory not found")
            continue
            
        for spacing in SPACING_STRATEGIES:
            for policy in LINK_POLICIES:
                try:
                    filename = generate_czml(size, analysis_dir, spacing, policy)
                    generated_files.append(filename)
                except Exception as e:
                    print(f"   ⚠️  Skipped {spacing}/{policy}/{size}: {e}")

print("\n" + "=" * 80)
print(f"GENERATED {len(generated_files)} CZML FILES")
print("=" * 80)
print("\nNow generating enhanced HTML viewer...")

# Generate enhanced viewer HTML
viewer_html = generate_enhanced_viewer(generated_files)

print("\n" + "=" * 80)
print("NEXT STEPS:")
print("=" * 80)
print("1. Start local server:")
print("   cd cesium_output")
print("   python3 -m http.server 8000 --bind 127.0.0.1")
print("2. Open in browser:")
print("   http://127.0.0.1:8000/constellation_viewer.html")
print("3. Use dropdown menus to switch between:")
print("   - Spacing strategies (orbit-spaced, close-orbit-spaced)")
print("   - Link policies (sticky, fifo)")
print("   - Constellation sizes (50, 100, 200 satellites)")

def generate_enhanced_viewer(czml_files):
    """Generate enhanced HTML viewer with multiple selection controls."""
    pass  # Will implement next
