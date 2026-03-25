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
        
        if(currentSat != nullptr) {
            bool currentSatVisible = false;
            for(const auto* sat : visibleSats) {
                if(sat == currentSat) {
                    currentSatVisible = true;
                    break;
                }
            }
            
            if(currentSatVisible) {
                const uint64_t currentBuf = satId2Sensor.at(currentSat->getID())->getBitsBuffered();
                if(currentBuf > 0) {
                    return currentSat;
                }
            }
        }
        
        auto& satQueue = gndId2SatQueue[groundStationId];
        
        std::set<uint32_t> visibleSatIds;
        for(const auto* sat : visibleSats) {
            visibleSatIds.insert(sat->getID());
        }
        
        std::set<uint32_t> queuedSatIds;
        for(const auto& queuedId : satQueue) {
            queuedSatIds.insert(queuedId);
        }
        
        for(const auto* sat : visibleSats) {
            uint32_t satId = sat->getID();
            
            if(queuedSatIds.find(satId) == queuedSatIds.end()) {
                satQueue.push_back(satId);
                queuedSatIds.insert(satId);
            }
        }
        
        while(!satQueue.empty()) {
            uint32_t frontSatId = satQueue.front();
            satQueue.pop_front();
            
            if(visibleSatIds.find(frontSatId) == visibleSatIds.end()) {
                continue;
            }
            
            if(satId2Occupied.count(frontSatId) && satId2Occupied.at(frontSatId)) {
                continue;
            }
            
            // Find the satellite object and check if it has data
            for(const auto* sat : visibleSats) {
                if(sat->getID() == frontSatId) {
                    const uint64_t buffered = satId2Sensor.at(frontSatId)->getBitsBuffered();
                    if(buffered > 0) {
                        return const_cast<cote::Satellite*>(sat);
                    }
                    break;
                }
            }
        }
        
        return nullptr;
    }
};
