#pragma once

#include <vector>
#include <map>
#include <deque>
#include <set>
#include "SchedulingPolicy.hpp"
#include <Satellite.hpp>
#include <Sensor.hpp>
#include <DateTime.hpp>

class FIFOPolicy : public SchedulingPolicy {
private:
    mutable std::map<uint32_t, std::deque<uint32_t>> gndId2SatQueue;
    
public:
    std::string getPolicyName() override {
        return "FIFO";
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
        
        // FIFO: Stick with current satellite until it's done or out of view
        if(currentSat != nullptr) {
            bool currentSatVisible = false;
            for(const auto* sat : visibleSats) {
                if(sat == currentSat) {
                    currentSatVisible = true;
                    break;
                }
            }
            
            // Check if current satellite still has data
            if(currentSatVisible) {
                const uint64_t currentBuf = satId2Sensor.at(currentSat->getID())->getBitsBuffered();
                if(currentBuf > 0) {
                    // Continue with current satellite - it's still visible and has data
                    return currentSat;
                }
            }
            // If we reach here, current satellite is either out of view or done with data
        }
        
        // Get queue for this ground station
        auto& satQueue = gndId2SatQueue[groundStationId];
        
        // Create set of visible satellite IDs for efficient lookup
        std::set<uint32_t> visibleSatIds;
        for(const auto* sat : visibleSats) {
            visibleSatIds.insert(sat->getID());
        }
        
        // Add new visible satellites to back of queue
        for(const auto* sat : visibleSats) {
            uint32_t satId = sat->getID();
            
            // Check if already in queue (O(n) but queues are small)
            bool alreadyInQueue = false;
            for(const auto& queuedId : satQueue) {
                if(queuedId == satId) {
                    alreadyInQueue = true;
                    break;
                }
            }
            
            if(!alreadyInQueue) {
                satQueue.push_back(satId);  // Add to back (FIFO order)
            }
        }
        
        // Process queue from front, removing invalid entries
        while(!satQueue.empty()) {
            uint32_t frontSatId = satQueue.front();
            satQueue.pop_front();
            
            // Skip if satellite is no longer visible
            if(visibleSatIds.find(frontSatId) == visibleSatIds.end()) {
                continue;  // Remove from queue and try next
            }
            
            // Find the satellite object and check if it has data
            for(const auto* sat : visibleSats) {
                if(sat->getID() == frontSatId) {
                    const uint64_t buffered = satId2Sensor.at(frontSatId)->getBitsBuffered();
                    if(buffered > 0) {
                        return const_cast<cote::Satellite*>(sat);
                    }
                    break;  // Found satellite but no data, continue to next
                }
            }
        }
        
        return nullptr;
    }
};
