#pragma once

#include <vector>
#include <map>
#include <queue>
#include <set>
#include "SchedulingPolicy.hpp"
#include <Satellite.hpp>
#include <Sensor.hpp>
#include <DateTime.hpp>

class FIFOPolicy : public SchedulingPolicy {
private:
    mutable std::map<uint32_t, std::queue<uint32_t>> gndId2SatQueue;
    mutable std::map<uint32_t, std::set<uint32_t>> gndId2SatInQueue;
    mutable std::map<uint32_t, uint64_t> gndId2ConnectionStartStep;
    uint64_t minConnectionSteps = 30;
    
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
        
        if(currentSat != NULL) {
            bool currentSatVisible = false;
            for(const auto* sat : visibleSats) {
                if(sat == currentSat) {
                    currentSatVisible = true;
                    break;
                }
            }
            
            uint64_t connectionSteps = stepCount - gndId2ConnectionStartStep[groundStationId];
            if(currentSatVisible && connectionSteps < minConnectionSteps) {
                return currentSat;
            }
        }
        
        for(const auto* sat : visibleSats) {
            uint32_t satId = sat->getID();
            if(gndId2SatInQueue[groundStationId].find(satId) == gndId2SatInQueue[groundStationId].end()) {
                gndId2SatQueue[groundStationId].push(satId);
                gndId2SatInQueue[groundStationId].insert(satId);
            }
        }
        
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
        
        while(!gndId2SatQueue[groundStationId].empty()) {
            uint32_t frontSatId = gndId2SatQueue[groundStationId].front();
            gndId2SatQueue[groundStationId].pop();
            
            for(const auto* sat : visibleSats) {
                if(sat->getID() == frontSatId) {
                    const uint64_t BUF = satId2Sensor.at(frontSatId)->getBitsBuffered();
                    if(BUF > 0) {
                        gndId2ConnectionStartStep[groundStationId] = stepCount;
                        return const_cast<cote::Satellite*>(sat);
                    }
                }
            }
        }
        
        return nullptr;
    }
};
