#ifndef FRAMESPACEDSTRATEGY_HPP
#define FRAMESPACEDSTRATEGY_HPP

#include "SpacingStrategy.hpp"
#include <utilities.hpp>

class FrameSpacedStrategy : public SpacingStrategy {
private:
    mutable size_t frameCount = 0;  // Track frame count
    mutable size_t satelliteCount = 0;  // Cache satellite count

public:
    FrameSpacedStrategy() = default;
    ~FrameSpacedStrategy() = default;

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
        // Frame-spaced logic: trigger when distance exceeds threshold
        return distanceKm >= thresholdKm;
    }

    void executeObservation(
        const std::vector<cote::Satellite>& satellites,
        std::map<uint32_t, cote::Sensor*>& satId2Sensor,
        std::map<uint32_t, double>& satId2ThresholdKm,
        double threshCoeff,
        const cote::DateTime& dateTime,
        cote::Log& log
    ) override {
        // Cache satellite count for use in updateFrameState
        satelliteCount = satellites.size();
        
        // Original frame-spaced logic: increment frame count
        frameCount++;
        
        // Only trigger all satellites when frameCount reaches constellation size
        if(frameCount % satellites.size() == 0) {
            frameCount = 0;  // Reset frame count
            
            log.evnt(cote::LogLevel::INFO, dateTime.toString(), "trigger-time");
            
            // Trigger ALL satellites at once (same as original frame-spaced.cpp)
            for(size_t i = 0; i < satellites.size(); i++) {
                satId2Sensor[satellites.at(i).getID()]->triggerSense();
                satId2ThresholdKm[satellites.at(i).getID()] =
                    threshCoeff * cote::util::calcAltitudeKm(satellites.at(i).getECIPosn());
            }
        }
        // Note: If frameCount % satellites.size() != 0, we don't trigger any satellites
        // This matches the original where only the lead satellite position is updated
    }

    void updateFrameState(
        uint32_t leadSatId,
        const std::array<double,3>& currPosn,
        const cote::DateTime& dateTime,
        std::map<uint32_t, cote::Sensor*>& satId2Sensor
    ) override {
        // Original frame-spaced logic: update lead satellite position when no sensing occurs
        // This happens when frameCount % satelliteCount != 0
        if(satelliteCount > 0 && frameCount % satelliteCount != 0) {
            satId2Sensor[leadSatId]->setPrevSensePosnDateTime(currPosn, dateTime);
        }
    }

    std::string getStrategyName() const override {
        return "frame-spaced";
    }
};

#endif