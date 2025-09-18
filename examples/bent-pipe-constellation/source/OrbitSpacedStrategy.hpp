#ifndef ORBITSPACEDSTRATEGY_HPP
#define ORBITSPACEDSTRATEGY_HPP

#include "SpacingStrategy.hpp"
#include <utilities.hpp>
#include <cmath>  // for fmod

class OrbitSpacedStrategy : public SpacingStrategy {
private:
    mutable size_t rotationIndex = 0;  // Simple rotation counter
    
    // Calculate which satellite should be active (simple round-robin)
    size_t calculateActiveSatellite(const std::vector<cote::Satellite>& satellites) const {
        // Each call rotates to the next satellite: 0,1,2,...,49,0,1,2...
        // This naturally distributes satellites over the simulation time
        size_t activeSatIndex = rotationIndex % satellites.size();
        rotationIndex++; // Move to next satellite for next trigger
        return activeSatIndex;
    }

public:
    OrbitSpacedStrategy() = default;
    ~OrbitSpacedStrategy() = default;

    bool shouldTriggerObservation(
        const std::array<double,3>& currPosn,
        const std::array<double,3>& prevSensePosn,
        const cote::DateTime& prevSenseDateTime,
        const cote::DateTime& currentDateTime,
        double distanceKm,
        double thresholdKm,
        uint32_t leadSatId,
        const std::vector<cote::Satellite>& satellites
    ) override {
        // Standard distance threshold check (same as bent-pipe)
        if (distanceKm < thresholdKm) {
            return false;
        }
        
        // Calculate which satellite should be active this trigger
        size_t activeSatIndex = rotationIndex % satellites.size();
        uint32_t activeSatId = satellites.at(activeSatIndex).getID();
        
        // Only trigger if the lead satellite is the currently active satellite
        return (leadSatId == activeSatId);
    }

    void executeObservation(
        const std::vector<cote::Satellite>& satellites,
        std::map<uint32_t, cote::Sensor*>& satId2Sensor,
        std::map<uint32_t, double>& satId2ThresholdKm,
        double threshCoeff,
        const cote::DateTime& dateTime,
        cote::Log& log
    ) override {
        // Get the currently active satellite (and advance rotation)
        size_t activeSatIndex = calculateActiveSatellite(satellites);
        uint32_t activeSatId = satellites.at(activeSatIndex).getID();
        
        log.evnt(cote::LogLevel::INFO, dateTime.toString(), "trigger-time");
        
        // Trigger only the active satellite for this observation
        satId2Sensor[activeSatId]->triggerSense();
        satId2ThresholdKm[activeSatId] = threshCoeff * cote::util::calcAltitudeKm(satellites.at(activeSatIndex).getECIPosn());
    }

    void updateFrameState(
        uint32_t leadSatId,
        const std::array<double,3>& currPosn,
        const cote::DateTime& dateTime,
        std::map<uint32_t, cote::Sensor*>& satId2Sensor
    ) override {
        // Orbit-spaced strategy: no frame state updates needed
        // Orbital phase is calculated from time, not maintained as state
    }

    std::string getStrategyName() const override {
        return "orbit-spaced";
    }
};

#endif
