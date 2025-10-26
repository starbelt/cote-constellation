#!/usr/bin/env python3
"""
Scan cesium_output for all CZML files and update the viewer HTML
"""
import json
from pathlib import Path
import re

def scan_czml_files():
    """Scan cesium_output directory for all CZML files"""
    czml_dir = Path("cesium_output")
    
    # Pattern: {spacing}_{policy}_{size}sats_{imagesize}mb.czml
    # Example: orbit-spaced_fifo_100sats_00279mb.czml
    pattern = re.compile(r'([\w-]+)_([\w]+)_(\d+)sats_(\w+)mb\.czml')
    
    files = {}
    for czml_file in czml_dir.glob("*.czml"):
        match = pattern.match(czml_file.name)
        if match:
            spacing, policy, size, imagesize = match.groups()
            key = f"{spacing}_{policy}_{size}_{imagesize}"
            files[key] = czml_file.name
    
    return files

def generate_javascript_config(files):
    """Generate JavaScript object for czmlFiles"""
    lines = ["        const czmlFiles = {"]
    
    for key in sorted(files.keys()):
        lines.append(f'            "{key}": "{files[key]}",')
    
    lines.append("        };")
    return "\n".join(lines)

def main():
    print("Scanning cesium_output for CZML files...")
    files = scan_czml_files()
    
    print(f"Found {len(files)} CZML files:")
    
    # Group by configuration for summary
    by_spacing = {}
    for key in files:
        spacing = key.split('_')[0]
        by_spacing[spacing] = by_spacing.get(spacing, 0) + 1
    
    for spacing, count in sorted(by_spacing.items()):
        print(f"  {spacing}: {count} files")
    
    # Generate JavaScript config
    js_config = generate_javascript_config(files)
    
    print(f"\n{'='*80}")
    print("JavaScript configuration (paste into constellation_viewer.html):")
    print(f"{'='*80}\n")
    print(js_config)
    print(f"\n{'='*80}\n")
    
    # Save to file
    config_file = Path("cesium_czml_config.js")
    with open(config_file, 'w') as f:
        f.write(js_config)
    
    print(f"✅ Saved to {config_file}")
    print(f"   Copy this into constellation_viewer.html around line 270")

if __name__ == "__main__":
    main()
