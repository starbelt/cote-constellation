#ifndef CLOSEORBITSPACEDSTRATEGY_HPP
#define CLOSEORBITSPACEDSTRATEGY_HPP

#include "SpacingStrategy.hpp"
#include <utilities.hpp>
#include <algorithm>  // for std::sort
#include <iomanip>    // for std::setfill, std::setw

class CloseOrbitSpacedStrategy : public SpacingStrategy {
public:
    CloseOrbitSpacedStrategy() = default;
    ~CloseOrbitSpacedStrategy() = default;

    // Constant 25 orbital positions with variable cluster density
    void initialize(std::vector<cote::Satellite>& satellites) {
        const size_t satCount = satellites.size();
        std::cout << "close-orbit-spaced: " << satCount << " satellites" << std::endl;
        
        if (satCount < 25) {
            std::cout << "  → " << satCount << " sats: no clustering" << std::endl;
            return;
        }
        
        if (satCount == 25) {
            std::cout << "  → 25 sats: baseline" << std::endl;
            return;
        }
        
        const double orbitalVelocity = 7.5;  // km/s
        size_t clusterSize;
        double targetSeparationKm;
        
        if (satCount == 50) {
            clusterSize = 2;
            targetSeparationKm = 6.0;
        } else if (satCount == 100) {
            clusterSize = 4;
            targetSeparationKm = 3.0;
        } else {
            clusterSize = 8;
            targetSeparationKm = 1.5;
        }
        
        const double timeOffsetSec = targetSeparationKm / orbitalVelocity;
        size_t clustersPositioned = 0;
        
        for (size_t i = 0; i < satCount; i += clusterSize) {
            cote::DateTime baseTime = satellites[i].getLocalTime();
            
            for (size_t j = 1; j < clusterSize && (i + j) < satCount; j++) {
                cote::DateTime followerTime = baseTime;
                advanceBySeconds(followerTime, j * timeOffsetSec);
                satellites[i + j].setLocalTime(followerTime);
            }
            clustersPositioned++;
        }
        
        std::cout << "  → Positioned " << clustersPositioned << " clusters of " << clusterSize 
                  << " satellites (" << targetSeparationKm << " km spacing)" << std::endl;
    }

private:
    static inline void advanceBySeconds(cote::DateTime& t, double dt) {
        long whole = static_cast<long>(std::floor(dt));
        long ns = static_cast<long>(std::llround((dt - whole) * 1e9));
        t.update(static_cast<uint8_t>(whole), static_cast<uint32_t>(ns));
    }

public:
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
        log.evnt(cote::LogLevel::INFO, dateTime.toString(), "trigger-time");
        for(size_t i = 0; i < satellites.size(); i++) {
            satId2Sensor[satellites.at(i).getID()]->triggerSense();
            satId2ThresholdKm[satellites.at(i).getID()] =
                threshCoeff * cote::util::calcAltitudeKm(satellites.at(i).getECIPosn());
        }
    }

    void updateFrameState(
        uint32_t leadSatId,
        const std::array<double,3>& currPosn,
        const cote::DateTime& dateTime,
        std::map<uint32_t, cote::Sensor*>& satId2Sensor
    ) override {
    }

    std::string getStrategyName() const override {
        return "close-orbit-spaced";
    }
};

#endif
