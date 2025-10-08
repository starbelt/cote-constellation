#ifndef CLOSEORBITSPACEDSTRATEGY_HPP
#define CLOSEORBITSPACEDSTRATEGY_HPP

#include "SpacingStrategy.hpp"
#include <utilities.hpp>
#include <cmath>
#include <algorithm>
#include <iostream>
#include <iomanip>

class CloseOrbitSpacedStrategy : public SpacingStrategy {
private:
    // Clustering parameters (calculated dynamically based on satellite count)
    int clusterSize = 5;              // satellites per cluster (calculated)
    double intraDtSec = 0.0;          // close-spaced inside cluster
    double interDtSec = 540.0;        // inter-cluster spacing (calculated)
    bool rephased = false;            // one-time initialization flag

    // Calculate optimal clustering parameters based on satellite count
    void calculateClusteringParams(int totalSats) {
        if (totalSats <= 1) {
            clusterSize = 1;
            interDtSec = 0.0;
            return;
        }
        
        // Define clustering strategy based on satellite count
        if (totalSats <= 50) {
            // For 50 or fewer satellites: 10 clusters of (totalSats/10) each
            clusterSize = std::max(1, totalSats / 10);
            // If not evenly divisible, adjust cluster size slightly
            if (totalSats % 10 != 0) {
                clusterSize = std::max(1, (totalSats + 9) / 10); // Round up
            }
        } else if (totalSats <= 100) {
            // For 100 satellites: 10 clusters of 10 each
            clusterSize = 10;
        } else {
            // For 200 satellites: 10 clusters of 20 each
            clusterSize = totalSats / 10;
        }
        
        // Calculate inter-cluster spacing based on orbital mechanics
        // Assumption: ~90 minutes orbital period, distribute clusters evenly
        int numClusters = (totalSats + clusterSize - 1) / clusterSize; // Round up
        interDtSec = (90.0 * 60.0) / numClusters; // 90 minutes / number of clusters
        
        std::cout << "CloseOrbitSpaced: " << totalSats << " sats → " 
                  << numClusters << " clusters of " << clusterSize 
                  << " (inter-spacing: " << std::fixed << std::setprecision(1) 
                  << interDtSec << "s)" << std::endl;
    }

    // Helper function to advance time by seconds
    static inline void advanceBySeconds(cote::DateTime& t, double dt) {
        long whole = static_cast<long>(std::floor(dt));
        long ns = static_cast<long>(std::llround((dt - whole) * 1e9));
        t.update(static_cast<uint8_t>(whole), static_cast<uint32_t>(ns));
    }

public:
    CloseOrbitSpacedStrategy() = default;
    ~CloseOrbitSpacedStrategy() = default;

    // One-time re-phasing to create orbit-spaced clusters
    void initialize(std::vector<cote::Satellite>& sats) {
        if (rephased) return;
        const int N = static_cast<int>(sats.size());
        
        // Calculate clustering parameters based on actual satellite count
        calculateClusteringParams(N);
        
        if (N <= 1 || clusterSize <= 1) { 
            rephased = true; 
            return; 
        }

        // Re-phase satellites into clusters
        for (int i = 1; i < N; ++i) {
            bool boundary = (i % clusterSize) == 0;
            double dt = boundary ? interDtSec : intraDtSec;

            auto t = sats[i-1].getLocalTime(); // get previous satellite's time
            advanceBySeconds(t, dt);           // advance by appropriate delta
            sats[i].setLocalTime(t);           // set new time
        }

        rephased = true;
    }

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
        // Close-orbit-spaced logic: trigger when distance exceeds threshold
        // This combines the orbital distribution approach with cluster-based sensing
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
        // Close-orbit-spaced logic: all satellites in constellation trigger simultaneously
        // The orbital clusters are defined by the constellation configuration file
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
        // Close-orbit-spaced strategy uses simultaneous triggering
        // No special frame state management needed
    }

    std::string getStrategyName() const override {
        return "close-orbit-spaced";
    }
};

#endif
