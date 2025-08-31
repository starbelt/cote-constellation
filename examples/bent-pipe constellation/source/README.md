# Satellite Downlink Scheduling Policies

This directory contains various scheduling policies for satellite-to-ground downlink operations. Each policy implements a different strategy for deciding which satellite a ground station should connect to at any given time.

## Policy Overview

### GreedyPolicy (original)
A simple greedy policy that maintains the current satellite connection as long as possible. Once connected to a satellite, it will not switch unless the satellite goes out of view. When no satellite is connected, it selects the visible satellite with the highest buffered data volume. This represents the original "bent-pipe" behavior where ground stations stick to their chosen satellite.

### FIFOPolicy (First-In-First-Out)
Implements a realistic First-In-First-Out queue-based scheduling system. Satellites are queued in the order they first become visible to each ground station. The policy maintains a minimum 30-second connection time before allowing switches, then moves to the next satellite in the FIFO queue. This ensures fair access based on arrival order while maintaining realistic connection durations.

### RandomPolicy
A randomized scheduler that selects satellites pseudo-randomly from the available options. It maintains the minimum 30-second connection time for realistic operations, then randomly chooses among visible satellites with data to download. Uses a fixed seed (42) for reproducible results across simulation runs.

### ShortestJobFirstPolicy (SJF)

### ShortestRemainingTimePolicy (SRTF)

### RoundRobinPolicy

## Common Features

## Usage

Policies are selected via command line argument when running the simulation:
```bash
./bent-pipe /path/to/config/ /path/to/logs/ [policy_name]
```

Supported policy names: `greedy`, `fifo`, `sjf`, `srtf`, `roundrobin`, `random`
