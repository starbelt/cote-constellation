#ifndef CLOSESPACEDSTRATEGY_HPP
#define CLOSESPACEDSTRATEGY_HPP

#include "SpacingStrategy.hpp"
#include <utilities.hpp>

class CloseSpacedStrategy : public SpacingStrategy {
private:
    size_t batchCount = 0;  // Track which batch of satellites should trigger
    static constexpr size_t BATCH_SIZE = 10;  // Satellites per batch (50/5 = 10 satellites per batch)
    static constexpr size_t TOTAL_BATCHES = 5;  // Number of batches

public:
    CloseSpacedStrategy() = default;
    ~CloseSpacedStrategy() = default;

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
        // Close-spaced logic: trigger every 1/5th of the normal threshold distance
        // This creates more frequent, smaller observation windows
        return distanceKm >= (thresholdKm / TOTAL_BATCHES);
    }

    void executeObservation(
        const std::vector<cote::Satellite>& satellites,
        std::map<uint32_t, cote::Sensor*>& satId2Sensor,
        std::map<uint32_t, double>& satId2ThresholdKm,
        double threshCoeff,
        const cote::DateTime& dateTime,
        cote::Log& log
    ) override {
        // Close-spaced logic: trigger only one batch of satellites at a time
        size_t startIdx = (batchCount % TOTAL_BATCHES) * BATCH_SIZE;
        size_t endIdx = std::min(startIdx + BATCH_SIZE, satellites.size());
        
        log.evnt(cote::LogLevel::INFO, dateTime.toString(), "trigger-time");
        
        for(size_t i = startIdx; i < endIdx; i++) {
            satId2Sensor[satellites.at(i).getID()]->triggerSense();
            satId2ThresholdKm[satellites.at(i).getID()] =
                threshCoeff * cote::util::calcAltitudeKm(satellites.at(i).getECIPosn());
        }
        
        batchCount++;  // Move to next batch for next trigger
    }

    void updateFrameState(
        uint32_t leadSatId,
        const std::array<double,3>& currPosn,
        const cote::DateTime& dateTime,
        std::map<uint32_t, cote::Sensor*>& satId2Sensor
    ) override {
        // Close-spaced strategy: no special frame state needed
        // Batching is handled in executeObservation
    }

    std::string getStrategyName() const override {
        return "close-spaced";
    }
};

#endif
