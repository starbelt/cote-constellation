#pragma once

#include <vector>
#include <map>
#include <queue>
#include <set>
#include "SchedulingPolicy.hpp"
#include <Satellite.hpp>
#include <Sensor.hpp>
#include <DateTime.hpp>

class RoundRobinPolicy : public SchedulingPolicy {
private:
    mutable std::map<uint32_t, std::queue<uint32_t>> gndId2SatQueue;
    mutable std::map<uint32_t, std::set<uint32_t>> gndId2SatInQueue;
    
public:
    std::string getPolicyName() override {
        return "RoundRobin";
    }
    
    cote::Satellite* makeSchedulingDecision(
        const std::vector<cote::Satellite*>& visibleSats,
        const std::map<uint32_t,cote::Sensor*>& satId2Sensor,
        const std::map<uint32_t,bool>& satId2Occupied,
        const cote::DateTime& currentTime,
        uint32_t groundStationId,
        cote::Satellite* currentSat,
        uint64_t stepCount
    ) override {
        
        // If we have a current satellite, check if we should continue with it
        if(currentSat != NULL) {
            bool currentSatVisible = false;
            for(const auto* sat : visibleSats) {
                if(sat == currentSat) {
                    currentSatVisible = true;
                    break;
                }
            }
            
            // Round Robin: continue with current satellite if visible AND has data
            if(currentSatVisible) {
                const uint64_t currentBuf = satId2Sensor.at(currentSat->getID())->getBitsBuffered();
                if(currentBuf > 0) {
                    return currentSat; // Continue with current satellite
                }
                // If buffer is 0, fall through to find next satellite
            }
        }
        
        // Add new visible satellites to the queue
        for(const auto* sat : visibleSats) {
            uint32_t satId = sat->getID();
            if(gndId2SatInQueue[groundStationId].find(satId) == gndId2SatInQueue[groundStationId].end()) {
                gndId2SatQueue[groundStationId].push(satId);
                gndId2SatInQueue[groundStationId].insert(satId);
            }
        }
        
        // Remove satellites that are no longer visible from both set and queue
        std::set<uint32_t> visibleSatIds;
        for(const auto* sat : visibleSats) {
            visibleSatIds.insert(sat->getID());
        }
        
        auto& satInQueue = gndId2SatInQueue[groundStationId];
        for(auto it = satInQueue.begin(); it != satInQueue.end();) {
            if(visibleSatIds.find(*it) == visibleSatIds.end()) {
                it = satInQueue.erase(it);
            } else {
                ++it;
            }
        }
        
        // Clean queue of non-visible satellites (fix queue/set drift)
        std::queue<uint32_t> cleanQueue;
        while(!gndId2SatQueue[groundStationId].empty()) {
            uint32_t satId = gndId2SatQueue[groundStationId].front();
            gndId2SatQueue[groundStationId].pop();
            if(visibleSatIds.count(satId)) {
                cleanQueue.push(satId);
            }
        }
        gndId2SatQueue[groundStationId] = cleanQueue;
        
        // Process queue to find next satellite with buffered data
        cote::Satellite* fallbackSat = nullptr;  // For maintaining connection when no data available
        
        // Track satellites we've already checked in this round to prevent infinite loops
        std::set<uint32_t> checkedSats;
        
        while(!gndId2SatQueue[groundStationId].empty()) {
            uint32_t frontSatId = gndId2SatQueue[groundStationId].front();
            gndId2SatQueue[groundStationId].pop();
            
            // If we've already checked this satellite in this round, skip to avoid infinite loop
            if(checkedSats.count(frontSatId)) {
                continue;
            }
            checkedSats.insert(frontSatId);
            
            // Find the satellite object
            for(const auto* sat : visibleSats) {
                if(sat->getID() == frontSatId) {
                    // Always consider this satellite as potential fallback
                    if(fallbackSat == nullptr) {
                        fallbackSat = const_cast<cote::Satellite*>(sat);
                    }
                    
                    // Check if satellite is occupied by another ground station
                    if(satId2Occupied.count(frontSatId) && satId2Occupied.at(frontSatId)) {
                        // Requeue occupied satellite for later attempts
                        gndId2SatQueue[groundStationId].push(frontSatId);
                        break; // Skip to next satellite
                    }
                    
                    const uint64_t BUF = satId2Sensor.at(frontSatId)->getBitsBuffered();
                    if(BUF > 0) {
                        // Re-add satellite to end of queue for true round-robin behavior
                        gndId2SatQueue[groundStationId].push(frontSatId);
                        return const_cast<cote::Satellite*>(sat);
                    } else {
                        // Satellite has no data - requeue it for later consideration
                        gndId2SatQueue[groundStationId].push(frontSatId);
                        // fallbackSat already set above
                    }
                    break;
                }
            }
        }
        
        // Fallback: maintain connection even when no data available
        if(fallbackSat != nullptr) {
            return fallbackSat;
        }
        
        // If current satellite is still visible but queue is empty, maintain connection
        if(currentSat != nullptr) {
            bool currentSatVisible = false;
            for(const auto* sat : visibleSats) {
                if(sat == currentSat) {
                    currentSatVisible = true;
                    break;
                }
            }
            if(currentSatVisible) {
                return currentSat; // Maintain connection to avoid flickering
            }
        }
        
        return nullptr;
    }
};
