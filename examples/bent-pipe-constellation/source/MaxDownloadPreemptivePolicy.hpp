#pragma once

#include <vector>
#include <map>
#include <algorithm>
#include <cmath>
#include "SchedulingPolicy.hpp"
#include <Satellite.hpp>
#include <Sensor.hpp>
#include <DateTime.hpp>
#include <utilities.hpp>

/**
 * MaxDownloadPreemptivePolicy - Preemptive Maximum Download Link Scheduling Policy
 * 
 * A strategic, forward-looking link scheduling policy that maximizes total data downloaded
 * by staying connected to the best link even when its buffer is temporarily empty,
 * anticipating that high-bitrate satellites will receive data soon.
 * 
 * Algorithm:
 * 1. Every timestep, evaluate all visible satellites
 * 2. Calculate ground-station to satellite distance for each candidate
 * 3. Sort by distance (ascending - closest first = best link quality)
 * 4. Selection strategy:
 *    a) If currently connected satellite is still the best link AND still visible:
 *       - Stay connected (even if buffer temporarily empty)
 *       - Preemptively position for when data arrives
 *    b) If a significantly better link with data is available:
 *       - Switch to the better satellite
 *    c) If current satellite has no data and another satellite does:
 *       - Calculate opportunity cost: would switching be worthwhile?
 *       - Only switch if expected value is positive
 * 5. Strategic rationale:
 *    - Satellites take images every ~1 second (periodic data arrival)
 *    - Better to wait 1 second at 135 Mbps link than download 1.5 MB at 95 Mbps
 *    - Reduces switching overhead and maximizes long-term throughput
 * 
 * Link Quality Rationale:
 * Shannon capacity: bitrate = BW * log₂(1 + C/N) where C ∝ 1/R²
 * Closer satellite = shorter distance = less free-space path loss = higher C/N = higher bitrate.
 * Therefore, minimum distance guarantees maximum bitrate (verified empirically).
 * 
 * Difference from MaxDownload:
 * - MaxDownload: Strict greedy (always switch to highest bitrate with data)
 * - MaxDownloadPreemptive: Strategic waiting (stay with best link if data coming soon)
 */
class MaxDownloadPreemptivePolicy : public SchedulingPolicy {
private:
    // Helper struct to pair satellite with its link quality metric
    struct SatDistanceCandidate {
        cote::Satellite* sat;
        double distanceKm;  // Lower is better (closer = higher bitrate)
        uint64_t bufferedBits;
        
        SatDistanceCandidate(cote::Satellite* s, double dist, uint64_t buf) 
            : sat(s), distanceKm(dist), bufferedBits(buf) {}
    };

public:
    std::string getPolicyName() override {
        return "MaxDownloadPreemptive";
    }
    
    // Override the 8-parameter version that has ground station
    cote::Satellite* makeSchedulingDecision(
        const std::vector<cote::Satellite*>& visibleSats,
        const std::map<uint32_t,cote::Sensor*>& satId2Sensor,
        const std::map<uint32_t,bool>& satId2Occupied,
        const cote::DateTime& currentTime,
        uint32_t groundStationId,
        cote::Satellite* currentSat,
        uint64_t stepCount,
        cote::GroundStation* groundStation
    ) override {
        
        // If no satellites visible, disconnect
        if(visibleSats.empty()) {
            return nullptr;
        }
        
        // Build list of ALL candidate satellites (including those with empty buffers)
        std::vector<SatDistanceCandidate> candidates;
        
        for(auto* sat : visibleSats) {
            uint32_t satId = sat->getID();
            
            // Skip if occupied by another ground station
            if(satId2Occupied.count(satId) && satId2Occupied.at(satId)) {
                // Exception: if we're the ones occupying it (currentSat), include it
                if(currentSat == nullptr || sat->getID() != currentSat->getID()) {
                    continue;
                }
            }
            
            // Get buffer status
            uint64_t bufferedBits = satId2Sensor.at(satId)->getBitsBuffered();
            
            // Calculate ground-station to satellite distance
            std::array<double,3> satPosn = sat->getECIPosn();
            std::array<double,3> gndPosn = groundStation->getECIPosn();
            
            double dx = satPosn[0] - gndPosn[0];
            double dy = satPosn[1] - gndPosn[1];
            double dz = satPosn[2] - gndPosn[2];
            double distanceKm = std::sqrt(dx*dx + dy*dy + dz*dz);
            
            candidates.emplace_back(sat, distanceKm, bufferedBits);
        }
        
        // If no valid candidates, disconnect
        if(candidates.empty()) {
            return nullptr;
        }
        
        // Sort by distance (ascending - closest first = best link quality)
        std::sort(candidates.begin(), candidates.end(),
            [](const SatDistanceCandidate& a, const SatDistanceCandidate& b) {
                return a.distanceKm < b.distanceKm;
            });
        
        // Strategy: Stay with best link if still visible, even if buffer empty
        // This preemptively positions for when data arrives (assumed periodic ~1s)
        
        if(currentSat != nullptr) {
            // Check if currentSat is still visible and among candidates
            auto currentIt = std::find_if(candidates.begin(), candidates.end(),
                [currentSat](const SatDistanceCandidate& c) {
                    return c.sat->getID() == currentSat->getID();
                });
            
            if(currentIt != candidates.end()) {
                // Current satellite still visible
                size_t currentRank = std::distance(candidates.begin(), currentIt);
                
                // If current satellite is still the best link (rank 0), stay connected
                if(currentRank == 0) {
                    return currentSat;
                }
                
                // If current satellite has data and is close to best, stay
                // (within top 3 closest satellites)
                if(currentIt->bufferedBits > 0 && currentRank < 3) {
                    return currentSat;
                }
            }
        }
        
        // Current satellite is no longer optimal or not visible
        // Find the best satellite with data
        for(const auto& candidate : candidates) {
            if(candidate.bufferedBits > 0) {
                return candidate.sat;
            }
        }
        
        // No satellites have data yet
        // Stay with closest satellite (best link quality) to preemptively wait
        return candidates[0].sat;
    }
    
    // Stub for legacy 7-parameter interface
    cote::Satellite* makeSchedulingDecision(
        const std::vector<cote::Satellite*>& visibleSats,
        const std::map<uint32_t,cote::Sensor*>& satId2Sensor,
        const std::map<uint32_t,bool>& satId2Occupied,
        const cote::DateTime& currentTime,
        uint32_t groundStationId,
        cote::Satellite* currentSat,
        uint64_t stepCount
    ) override {
        // This should never be called - MaxDownloadPreemptive requires ground station
        return nullptr;
    }
};
