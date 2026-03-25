# Bent-Pipe Constellation Analysis

This example sweeps through constellation populations and link policies to evaluate
space-to-ground satellite communications performance across different configurations.

**Paper:** Link Policies for Scheduling Space-to-Ground Satellite Communications  
**Conference:** ACM HotNets 2026  
**Authors:** Chris Cheshire and Bradley Denby

## Quick Start

### Run Simulations

```bash
# Compile and run simulations (see build/README.md)
cd build && make && ./bent-pipe ../configuration ../logs sticky orbit-spaced
```

### Run Temporal Analysis

```bash
# Automated analysis of all results
./run_temporal_analysis.sh

# Or run individual analyses
python temporal_geographic_analysis.py
python temporal_pattern_analysis.py
python regional_analysis.py
```

## 3D Constellation Visualizer (Paper Artifact)

An interactive CesiumJS-based 3D globe visualization that shows satellite orbits,
ground station contacts, link-policy scheduling decisions, and per-satellite
buffer/download state over time.

### Prerequisites

| Requirement | Notes |
|---|---|
| **Python 3.10+** | For simulation, CZML generation, and local HTTP server |
| **pandas** | `pip install pandas` |
| **CoTE build** | `cd build && make -j8` (see [build/README.md](build/README.md)) |
| **Web browser** | Chrome / Firefox / Safari (needs `DecompressionStream` support) |
| **Cesium Ion token** | Free at <https://ion.cesium.com/tokens> — paste into `constellation_viewer.html` |

### Step-by-step

```bash
# 1. Run a CoTE simulation (example: geobinv5, 25 sats, close-spaced, 2.8 MB images)
cd examples/bent-pipe-constellation
bash run_analysis.sh geobinv5 25 close-spaced 02799

# 2. Generate CZML visualization data from the simulation output
#    The analysis_dir is the timestamped directory created by run_analysis.sh
#    (check results/<your_results_dir>/ for the directory name)
python generate_single_czml.py \
    <analysis_dir> close-spaced geobinv5 25

#    Or generate CZML for ALL policies/spacings at once:
bash generate_all_czml.sh

# 3. Start a local HTTP server (required for browser to load .czml.gz files)
python -m http.server 8080

# 4. Open the viewer in your browser
#    http://localhost:8080/constellation_viewer.html
```

### Viewer controls

| Control | Description |
|---|---|
| **Spacing / Policy / Size / Image** dropdowns | Select a configuration |
| **Load Visualization** button | Fetch & decompress the CZML, animate on the globe |
| **Show Labels** | Toggle satellite ID labels |
| **Show Lines** | Toggle green ground-station connection lines |
| **Queue panel** (top-right) | Live list of in-view satellites and buffer sizes |
| **Click a satellite** | Inspect lat/lon/alt, buffer, downloaded MB |
| Timeline scrubber | Drag or press play to advance simulation time |

### File overview

| File | Purpose |
|---|---|
| `constellation_viewer.html` | CesiumJS 3D viewer (single self-contained HTML) |
| `generate_single_czml.py` | Convert one policy's visibility_log.csv → compressed CZML |
| `generate_all_czml.sh` | Batch-generate CZML for every combination in results/ |
| `run_analysis.sh` | Run CoTE simulation(s) with configurable parameters |
| `cesium_output/` | Generated `.czml.gz` files loaded by the viewer |

---

## Directory Contents

### Core Simulation
* [build](build/README.md): Compile and run the program
* [configuration](configuration/README.md): Program configuration files
* [source](source/bent-pipe.cpp): Implementation files
* [scripts](scripts/README.md): Support scripts for configuration generation

### Analysis Tools

#### Original Analysis (Total Data Down Focus)
* `figure2.py` - Total data downlinked comparison
* `analyze_starvation_data.py` - Satellite starvation analysis
* `analyze_optimality.py` - Throughput optimization analysis
* `plot_*.py` - Various visualization scripts

#### New Temporal Analysis (Geographic and Temporal Focus)
* **`temporal_geographic_analysis.py`** - Geographic coverage and equity metrics
* **`temporal_pattern_analysis.py`** - Temporal quality and freshness metrics
* **`regional_analysis.py`** - Regional performance and latitudinal bias
* **`run_temporal_analysis.sh`** - Automated execution of all analyses

### Documentation
* **[TEMPORAL_ANALYSIS_README.md](TEMPORAL_ANALYSIS_README.md)** - Complete guide to temporal analysis tools
* **[PAPER_INTEGRATION_GUIDE.md](PAPER_INTEGRATION_GUIDE.md)** - Guide for integrating analysis into paper
* **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** - Quick reference for common tasks
* **[TEMPORAL_ANALYSIS_SUMMARY.md](TEMPORAL_ANALYSIS_SUMMARY.md)** - Complete summary of analysis capabilities
* [README.md](README.md): This document

### Results
* [results](results/): Simulation outputs (visibility logs, CZML, etc.)
* [logs](logs/README.md): Destination directory for program logs

## Analysis Capabilities

### Original Metrics (Throughput Focus)
- ✅ Total data downlinked (GB)
- ✅ Ground station idle time (%)
- ✅ Satellite starvation (binary)
- ✅ Contention (# satellites visible)

### New Metrics (Temporal and Geographic Focus)
- 🆕 **Geographic equity** (Gini coefficient)
- 🆕 **Coverage extent** (# unique cells)
- 🆕 **Data freshness** (capture→downlink latency)
- 🆕 **Coverage gaps** (max time without observation)
- 🆕 **Revisit times** (time between location revisits)
- 🆕 **Service windows** (connection durations)
- 🆕 **Regional performance** (per-region coverage)
- 🆕 **Latitudinal bias** (coverage by latitude)

## Key Results

### Throughput (Original Paper Finding)
**MaxDL provides 3-4× higher total data downlink compared to baseline policies**

### Geographic Equity (New Finding)
**MaxDL maintains geographic equity (Gini < 0.X) while maximizing throughput**

### Data Freshness (New Finding)
**MaxDL reduces median freshness by XX% compared to Sticky policy**

### Regional Fairness (New Finding)
**Orbit-spaced configurations provide XX% more equitable coverage across regions**

## Configurations Analyzed

### Spacing Strategies
- **Close-spaced**: All satellites in same ground track frame (~12km apart)
- **Frame-spaced**: Satellites separated by one ground track frame
- **Orbit-spaced**: Satellites distributed evenly across entire orbit
- **Close-orbit-spaced**: Clusters of close-spaced satellites distributed across orbit

### Link Policies
- **Sticky**: Connect to first visible satellite, maintain connection
- **FIFO**: Sticky + disconnect when buffer drains
- **Round Robin**: FIFO + 30-second time slices
- **Random**: Round Robin + random satellite selection
- **MinDistance**: Choose closest satellite with data
- **MaxDL**: Maximize expected downlink (bitrate × buffer)
- **GeoBin V5**: Geographic-bin-aware scheduling for coverage equity

### Parameter Sweeps
- **Satellite counts**: 1, 15, 25, 50, 100, 200
- **Image sizes**: 27 KB, 279 KB, 2.8 MB, 28 MB, 280 MB, 1 GB
- **Total configurations**: 6 × 6 × 4 = 144 (per image size × sat count combination)

## Paper Integration

See [PAPER_INTEGRATION_GUIDE.md](PAPER_INTEGRATION_GUIDE.md) for detailed instructions on:
- Adding new sections to paper
- Generating figures and tables
- Computing key statistics
- Validating results

## Dependencies

### C++ (Simulation)
- GCC 8+ (C++17 support)
- COTE library (included in repository)

### Python (Analysis)
```bash
pip install pandas numpy matplotlib seaborn scipy
```

## Citation

```bibtex
@inproceedings{cheshire2026linkpolicies,
  title={Link Policies for Scheduling Space-to-Ground Satellite Communications},
  author={Cheshire, Chris and Denby, Bradley},
  booktitle={ACM Workshop on Hot Topics in Networks (HotNets)},
  year={2026}
}
```

## Contributors

**Original Simulation:**
- Bradley Denby (bdenby@vt.edu)

**Link Policies and Analysis:**
- Chris Cheshire (chrischeshire@vt.edu)

**Temporal and Geographic Analysis:**
- Chris Cheshire (chrischeshire@vt.edu)

## License

See the top-level LICENSE file for the license.
