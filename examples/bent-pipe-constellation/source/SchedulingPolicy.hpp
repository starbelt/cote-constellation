#ifndef SCHEDULING_POLICY_HPP
#define SCHEDULING_POLICY_HPP

#include <vector>
#include <map>
#include <deque>
#include <string>
#include <Satellite.hpp>
#include <GroundStation.hpp>
#include <Sensor.hpp>
#include <DateTime.hpp>
#include "ImageMetadata.hpp"

class SchedulingPolicy {
public:
    // 10-parameter interface (with image queue)
    virtual cote::Satellite* makeSchedulingDecision(
        const std::vector<cote::Satellite*>& visibleSats,
        const std::map<uint32_t,cote::Sensor*>& satId2Sensor,
        const std::map<uint32_t,bool>& satId2Occupied,
        const cote::DateTime& currentTime,
        uint32_t groundStationId,
        cote::Satellite* currentSat,
        uint64_t stepCount,
        cote::GroundStation* groundStation,
        const std::map<uint32_t,double>& satId2BitrateMbps,
        const std::map<uint32_t, std::deque<ImageMetadata>>& satId2ImageQueue
    ) {
        // Default: delegate to 9-parameter version
        return makeSchedulingDecision(visibleSats, satId2Sensor, satId2Occupied,
                                     currentTime, groundStationId, currentSat, stepCount,
                                     groundStation, satId2BitrateMbps);
    }
    
    // 9-parameter interface (with bitrate)
    virtual cote::Satellite* makeSchedulingDecision(
        const std::vector<cote::Satellite*>& visibleSats,
        const std::map<uint32_t,cote::Sensor*>& satId2Sensor,
        const std::map<uint32_t,bool>& satId2Occupied,
        const cote::DateTime& currentTime,
        uint32_t groundStationId,
        cote::Satellite* currentSat,
        uint64_t stepCount,
        cote::GroundStation* groundStation,
        const std::map<uint32_t,double>& satId2BitrateMbps
    ) {
        // Default: delegate to 8-parameter version
        return makeSchedulingDecision(visibleSats, satId2Sensor, satId2Occupied,
                                     currentTime, groundStationId, currentSat, stepCount, groundStation);
    }
    
    // 8-parameter interface (with ground station)
    virtual cote::Satellite* makeSchedulingDecision(
        const std::vector<cote::Satellite*>& visibleSats,
        const std::map<uint32_t,cote::Sensor*>& satId2Sensor,
        const std::map<uint32_t,bool>& satId2Occupied,
        const cote::DateTime& currentTime,
        uint32_t groundStationId,
        cote::Satellite* currentSat,
        uint64_t stepCount,
        cote::GroundStation* groundStation
    ) {
        // Default: delegate to 7-parameter version
        return makeSchedulingDecision(visibleSats, satId2Sensor, satId2Occupied,
                                     currentTime, groundStationId, currentSat, stepCount);
    }
    
    // 7-parameter interface (base)
    virtual cote::Satellite* makeSchedulingDecision(
        const std::vector<cote::Satellite*>& visibleSats,
        const std::map<uint32_t,cote::Sensor*>& satId2Sensor,
        const std::map<uint32_t,bool>& satId2Occupied,
        const cote::DateTime& currentTime,
        uint32_t groundStationId,
        cote::Satellite* currentSat,
        uint64_t stepCount
    ) = 0;
    
    virtual std::string getPolicyName() = 0;
    virtual ~SchedulingPolicy() = default;
};

#endif
