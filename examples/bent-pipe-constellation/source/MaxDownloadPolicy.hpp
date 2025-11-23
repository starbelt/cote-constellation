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
 * MaxDownloadPolicy - Maximum Download Link Scheduling Policy
 * 
 * A greedy, space-aware link scheduling policy that maximizes total data downloaded
 * by always connecting to the satellite with the best link (highest bitrate) that has data.
 * 
 * Algorithm:
 * 1. Every timestep, evaluate all visible satellites
 * 2. Calculate ground-station to satellite distance for each candidate
 * 3. Sort by distance (ascending - closest first = best link quality)
 * 4. Select the closest satellite that:
 *    - Is not occupied by another ground station
 *    - Has data in its buffer (> 0 bits)
 * 5. Switch immediately if a better link with data becomes available
 * 
 * This policy is saturation-aware: if the best satellite has no data,
 * it automatically falls back to the next best satellite with data.
 * 
 * Link Quality Rationale:
 * Shannon capacity: bitrate = BW * log₂(1 + C/N) where C ∝ 1/R²
 * Closer satellite = shorter distance = less free-space path loss = higher C/N = higher bitrate.
 * Therefore, minimum distance guarantees maximum bitrate (verified empirically).
 * Distance accounts for both orbital geometry and ground-station elevation angle.
 * 
 * Note: Distance is calculated from ground station to satellite (signal path length),
 * which accurately captures link quality. Atmospheric loss is constant in this simulation.
 */
class MaxDownloadPolicy : public SchedulingPolicy {
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
        return "MaxDownload";
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
        
        // Build list of candidate satellites ranked by distance (lower = better link)
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
            
            // STRICT MODE: Only consider satellites with data
            // Skip satellites with empty buffers (even if currently connected)
            if(bufferedBits == 0) {
                continue;
            }
            
            // Calculate ground-station to satellite distance
            // This is the actual signal path length - lower = better link quality
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
                return a.distanceKm < b.distanceKm;  // Lower distance = better
            });
        
        // Return the best candidate (closest distance with data)
        // In strict mode, all candidates already have data (bufferedBits > 0)
        if(!candidates.empty()) {
            return candidates[0].sat;
        }
        
        // No satellites with data available - disconnect
        return nullptr;
    }
    
    // Stub for legacy 7-parameter interface (never called since we override 8-param version)
    cote::Satellite* makeSchedulingDecision(
        const std::vector<cote::Satellite*>& visibleSats,
        const std::map<uint32_t,cote::Sensor*>& satId2Sensor,
        const std::map<uint32_t,bool>& satId2Occupied,
        const cote::DateTime& currentTime,
        uint32_t groundStationId,
        cote::Satellite* currentSat,
        uint64_t stepCount
    ) override {
        // This should never be called - MaxDownload requires ground station
        return nullptr;
    }
};

