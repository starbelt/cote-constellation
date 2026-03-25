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
    mutable std::map<uint32_t, uint64_t> gndId2ConnectStep;
    
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
        
        if(currentSat != NULL) {
            bool currentSatVisible = false;
            for(const auto* sat : visibleSats) {
                if(sat == currentSat) {
                    currentSatVisible = true;
                    break;
                }
            }
            
            // Continue with current satellite if visible, has data, and under 30s
            if(currentSatVisible) {
                const uint64_t currentBuf = satId2Sensor.at(currentSat->getID())->getBitsBuffered();
                const uint64_t elapsed = stepCount - gndId2ConnectStep[groundStationId];
                if(currentBuf > 0 && elapsed < 30) {
                    return currentSat;
                }
                if(currentBuf > 0) {
                    uint32_t curId = currentSat->getID();
                    if(gndId2SatInQueue[groundStationId].find(curId) == gndId2SatInQueue[groundStationId].end()) {
                        gndId2SatQueue[groundStationId].push(curId);
                        gndId2SatInQueue[groundStationId].insert(curId);
                    }
                }
            }
        }
        
        for(const auto* sat : visibleSats) {
            uint32_t satId = sat->getID();
            if(gndId2SatInQueue[groundStationId].find(satId) == gndId2SatInQueue[groundStationId].end()) {
                gndId2SatQueue[groundStationId].push(satId);
                gndId2SatInQueue[groundStationId].insert(satId);
            }
        }
        
        // Remove satellites no longer visible
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
        
        // Clean queue of non-visible satellites
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
        cote::Satellite* fallbackSat = nullptr;
        
        std::set<uint32_t> checkedSats;
        
        while(!gndId2SatQueue[groundStationId].empty()) {
            uint32_t frontSatId = gndId2SatQueue[groundStationId].front();
            gndId2SatQueue[groundStationId].pop();
            
            if(checkedSats.count(frontSatId)) {
                continue;
            }
            checkedSats.insert(frontSatId);
            
            for(const auto* sat : visibleSats) {
                if(sat->getID() == frontSatId) {
                    if(fallbackSat == nullptr) {
                        fallbackSat = const_cast<cote::Satellite*>(sat);
                    }
                    
                    if(satId2Occupied.count(frontSatId) && satId2Occupied.at(frontSatId)) {
                        gndId2SatQueue[groundStationId].push(frontSatId);
                        break;
                    }
                    
                    const uint64_t BUF = satId2Sensor.at(frontSatId)->getBitsBuffered();
                    if(BUF > 0) {
                        // Re-add to end for round-robin
                        gndId2SatQueue[groundStationId].push(frontSatId);
                        gndId2ConnectStep[groundStationId] = stepCount;
                        return const_cast<cote::Satellite*>(sat);
                    } else {
                        gndId2SatQueue[groundStationId].push(frontSatId);
                    }
                    break;
                }
            }
        }
        
        if(fallbackSat != nullptr) {
            gndId2ConnectStep[groundStationId] = stepCount;
            return fallbackSat;
        }
        
        if(currentSat != nullptr) {
            bool currentSatVisible = false;
            for(const auto* sat : visibleSats) {
                if(sat == currentSat) {
                    currentSatVisible = true;
                    break;
                }
            }
            if(currentSatVisible) {
                gndId2ConnectStep[groundStationId] = stepCount;
                return currentSat;
            }
        }
        
        return nullptr;
    }
};
