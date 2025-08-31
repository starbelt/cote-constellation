# Satellite Downlink Scheduling Policies

This directory contains various scheduling policies for satellite-to-ground downlink operations. Each policy implements a different strategy for deciding which satellite a ground station should connect to at any given time.

## Policy Overview

### GreedyPolicy (original)
A simple greedy policy that maintains the current satellite connection as long as possible. Once connected to a satellite, it will not switch unless the satellite goes out of view. When no satellite is connected, it selects the visible satellite with the highest buffered data volume. This represents the original "bent-pipe" behavior where ground stations stick to their chosen satellite.

### FIFOPolicy (True First-In-First-Out)
Implements First-In-First-Out queue-based scheduling system. Satellites are queued in the order they first become visible to each ground station. Unlike Round Robin, FIFO only switches satellites when:
- The current satellite finishes downloading all its buffered data, OR
- The current satellite goes out of view

This ensures satellites are served to completion in the order they arrived, which can lead to some satellites receiving longer uninterrupted download sessions.

### RoundRobinPolicy (Time-Sliced FIFO)
Implements a time-sliced Round Robin scheduling system. Satellites are queued in the order they first become visible, but unlike true FIFO, this policy enforces a maximum time slice (30 time steps) per satellite. After the time slice expires, it moves to the next satellite in the queue even if the current satellite still has data to download. This ensures more equitable time distribution among satellites but may fragment download sessions.

### RandomPolicy
A randomized scheduler that selects satellites pseudo-randomly from the available options. It maintains the minimum 30-second connection time for realistic operations, then randomly chooses among visible satellites with data to download. Uses a fixed seed (42) for reproducible results across simulation runs.

### ShortestJobFirstPolicy (SJF)

### ShortestRemainingTimePolicy (SRTF)

## Key Differences: FIFO vs Round Robin

The fundamental difference between these policies lies in their switching behavior:

- **FIFO**: Satellites are served to completion (or until out of view). More efficient for individual satellites but potentially less fair.
- **Round Robin**: Fixed time slices ensure all satellites get regular access. More fair but potentially less efficient due to switching overhead.

## Performance Comparison

Based on test scenarios:
- **Greedy**: ~12.7 GB total download, minimal satellite switching (sticks to best satellite)
- **FIFO**: ~12.7 GB total download, switches only when satellites complete or lose visibility
- **Round Robin**: ~12.8 GB total download, regular switching every 30 time steps

## Common Features

## Usage

Policies are selected via command line argument when running the simulation:
```bash
./bent-pipe /path/to/config/ /path/to/logs/ [policy_name]
```

Supported policy names: `greedy`, `fifo`, `sjf`, `srtf`, `roundrobin`, `random`
