#pragma once

#include <vector>
#include <map>
#include <deque>
#include <algorithm>
#include <cmath>
#include <limits>
#include <string>
#include "SchedulingPolicy.hpp"
#include <Satellite.hpp>
#include <GroundStation.hpp>
#include <Sensor.hpp>
#include <DateTime.hpp>
#include <utilities.hpp>
#include "ImageMetadata.hpp"

class GeoBinPolicy : public SchedulingPolicy {
private:
    static constexpr double BIN_SIZE_DEG  = 1.0;
    static constexpr int    NUM_LAT_BINS  = 180;
    static constexpr int    NUM_LON_BINS  = 360;
    static constexpr double MIN_ELEV_DEG  = 10.0;
    static constexpr double EARTH_RADIUS_KM = 6371.0;
    static constexpr double COMPLETION_MARGIN = 0.85;

    std::map<int, int> binDownloadCount;
    std::map<int, int> binInFlightCount;
    std::map<uint32_t, int> satReservedBin;

    mutable uint32_t currentDownloadingSatId = 0;
    mutable bool hasPartialDownload = false;

    int totalImagesDownloaded = 0;
    double totalFreshnessSeconds = 0.0;

    int latLonToBinId(double lat_deg, double lon_deg) const {
        lat_deg = std::max(-90.0, std::min(90.0, lat_deg));
        while (lon_deg < -180.0) lon_deg += 360.0;
        while (lon_deg >  180.0) lon_deg -= 360.0;

        int lat_bin = static_cast<int>(std::floor((lat_deg + 90.0) / BIN_SIZE_DEG));
        int lon_bin = static_cast<int>(std::floor((lon_deg + 180.0) / BIN_SIZE_DEG));

        lat_bin = std::max(0, std::min(NUM_LAT_BINS - 1, lat_bin));
        lon_bin = std::max(0, std::min(NUM_LON_BINS - 1, lon_bin));

        return lat_bin * NUM_LON_BINS + lon_bin;
    }

    int getBinCount(int binId) const {
        int count = 0;
        auto it = binDownloadCount.find(binId);
        if (it != binDownloadCount.end()) count += it->second;
        auto it2 = binInFlightCount.find(binId);
        if (it2 != binInFlightCount.end()) count += it2->second;
        return count;
    }

    int getBinCount(const ImageMetadata& img) const {
        return getBinCount(latLonToBinId(img.captureLat, img.captureLon));
    }

    /**
     * Parse timestamp to seconds-since-epoch.
     */
    double parseTimestampToSeconds(const std::string& timestamp) const {
        try {
            if (timestamp.length() < 19) return 0.0;
            int year   = std::stoi(timestamp.substr(0, 4));
            int month  = std::stoi(timestamp.substr(5, 2));
            int day    = std::stoi(timestamp.substr(8, 2));
            int hour   = std::stoi(timestamp.substr(11, 2));
            int minute = std::stoi(timestamp.substr(14, 2));
            double sec = std::stod(timestamp.substr(17));

            double days = (year - 1970) * 365.25 + (month - 1) * 30.44 + day;
            return days * 86400.0 + hour * 3600.0 + minute * 60.0 + sec;
        } catch (...) {
            return 0.0;
        }
    }

    double computeDownloadTimeSec(const ImageMetadata& img, double bitrateBps) const {
        if (bitrateBps <= 0.0) return std::numeric_limits<double>::infinity();
        return static_cast<double>(img.sizeBits) / bitrateBps;
    }

    double estimateRemainingPassSecondsImpl(
        const cote::Satellite* sat,
        const cote::GroundStation* gs,
        double JD, uint32_t SEC, uint32_t NS
    ) const {
        double gsLat = gs->getLatitude();
        double gsLon = gs->getLongitude();
        double gsHAE = gs->getHAE();
        std::array<double,3> satPosn = sat->getECIPosn();

        double elevDeg = cote::util::calcElevationDeg(
            JD, SEC, NS, gsLat, gsLon, gsHAE, satPosn
        );

        if (elevDeg < MIN_ELEV_DEG) return 0.0;

        double altKm = cote::util::calcAltitudeKm(satPosn);
        double sma = EARTH_RADIUS_KM + altKm;
        double orbitalPeriodSec = 2.0 * M_PI * std::sqrt(
            sma * sma * sma / 398600.4418
        );

        double passDurationSec = orbitalPeriodSec * 0.06;

        double elevFraction = (elevDeg - MIN_ELEV_DEG) / (90.0 - MIN_ELEV_DEG);
        double remainingSec = passDurationSec * 0.5 *
            std::sin(elevFraction * M_PI);

        return remainingSec * COMPLETION_MARGIN;
    }

    bool canCompleteDownload(
        const ImageMetadata& img,
        double bitrateBps,
        double remainingPassSec
    ) const {
        if (bitrateBps <= 0.0 || remainingPassSec <= 0.0) return false;
        double downloadTimeSec = static_cast<double>(img.sizeBits) / bitrateBps;
        return downloadTimeSec <= remainingPassSec;
    }

public:
    std::string getPolicyName() override {
        return "GeoBin";
    }

    double estimateRemainingPassSeconds(
        const cote::Satellite* sat,
        const cote::GroundStation* gs,
        double JD, uint32_t SEC, uint32_t NS
    ) const {
        return estimateRemainingPassSecondsImpl(sat, gs, JD, SEC, NS);
    }

    void notifyImageStarted(uint32_t satId) {
        currentDownloadingSatId = satId;
        hasPartialDownload = true;
    }

    /**
     * Reserve a bin for cross-satellite coordination.
     */
    void reserveDownload(uint32_t satId, double lat, double lon) {
        int newBinId = latLonToBinId(lat, lon);

        auto it = satReservedBin.find(satId);
        if (it != satReservedBin.end()) {
            if (it->second == newBinId) return;
            binInFlightCount[it->second]--;
            if (binInFlightCount[it->second] <= 0)
                binInFlightCount.erase(it->second);
        }
        binInFlightCount[newBinId]++;
        satReservedBin[satId] = newBinId;
    }

    void notifyImageCompleted(double lat, double lon, uint32_t satId) {
        int binId = latLonToBinId(lat, lon);
        binDownloadCount[binId]++;
        totalImagesDownloaded++;

        auto it = satReservedBin.find(satId);
        if (it != satReservedBin.end()) {
            binInFlightCount[it->second]--;
            if (binInFlightCount[it->second] <= 0)
                binInFlightCount.erase(it->second);
            satReservedBin.erase(it);
        }

        hasPartialDownload = false;
        currentDownloadingSatId = 0;
    }

    int getFilledBinCount() const {
        int count = 0;
        for (const auto& kv : binDownloadCount) {
            if (kv.second > 0) count++;
        }
        return count;
    }

    int getTotalDownloads() const { return totalImagesDownloaded; }

    void reorderQueueForDiversity(
        std::deque<ImageMetadata>& queue,
        double bitrateBps = 0.0,
        double remainingPassSec = 0.0
    ) {
        if (queue.size() <= 1) return;

        if (queue.front().sizeBits < queue.front().originalSizeBits) {
            return;
        }

        bool useFeasibilityFilter = (bitrateBps > 0.0 && remainingPassSec > 0.0);

        size_t bestIdx = 0;
        int    bestBinCount = std::numeric_limits<int>::max();
        double bestDownloadTime = std::numeric_limits<double>::infinity();
        double bestFresh = -1.0;
        bool   foundViable = false;

        for (size_t i = 0; i < queue.size(); i++) {
            if (useFeasibilityFilter &&
                !canCompleteDownload(queue[i], bitrateBps, remainingPassSec)) {
                continue;
            }

            int bc = getBinCount(queue[i]);
            double dlTime = computeDownloadTimeSec(queue[i], bitrateBps);
            double fresh = parseTimestampToSeconds(queue[i].timestamp);

            if (!foundViable) {
                bestBinCount = bc;
                bestDownloadTime = dlTime;
                bestFresh = fresh;
                bestIdx = i;
                foundViable = true;
            } else if (bc < bestBinCount) {
                bestBinCount = bc;
                bestDownloadTime = dlTime;
                bestFresh = fresh;
                bestIdx = i;
            } else if (bc == bestBinCount) {
                if (dlTime < bestDownloadTime) {
                    bestDownloadTime = dlTime;
                    bestFresh = fresh;
                    bestIdx = i;
                } else if (std::abs(dlTime - bestDownloadTime) < 1e-6) {
                    if (fresh > bestFresh) {
                        bestFresh = fresh;
                        bestIdx = i;
                    }
                }
            }
        }

        if (!foundViable) {
            return;
        }

        if (bestIdx != 0) {
            ImageMetadata bestImage = queue[bestIdx];
            queue.erase(queue.begin() + bestIdx);
            queue.push_front(bestImage);
        }
    }

    cote::Satellite* makeSchedulingDecision(
        const std::vector<cote::Satellite*>& visibleSats,
        const std::map<uint32_t, cote::Sensor*>& satId2Sensor,
        const std::map<uint32_t, bool>& satId2Occupied,
        const cote::DateTime& currentTime,
        uint32_t groundStationId,
        cote::Satellite* currentSat,
        uint64_t stepCount,
        cote::GroundStation* groundStation,
        const std::map<uint32_t, double>& satId2BitrateMbps,
        const std::map<uint32_t, std::deque<ImageMetadata>>& satId2ImageQueue
    ) override {

        if (hasPartialDownload && currentDownloadingSatId != 0) {
            for (const auto* sat : visibleSats) {
                if (sat->getID() == currentDownloadingSatId) {
                    const uint32_t SAT_ID = sat->getID();
                    const uint64_t BUF = satId2Sensor.at(SAT_ID)->getBitsBuffered();
                    if (BUF > 0) {
                        return const_cast<cote::Satellite*>(sat);
                    }
                    hasPartialDownload = false;
                    currentDownloadingSatId = 0;
                    break;
                }
            }
            hasPartialDownload = false;
            currentDownloadingSatId = 0;
        }

        const double JD = cote::util::calcJulianDayFromYMD(
            currentTime.getYear(), currentTime.getMonth(), currentTime.getDay()
        );
        const uint32_t SEC = cote::util::calcSecSinceMidnight(
            currentTime.getHour(), currentTime.getMinute(),
            currentTime.getSecond()
        );
        const uint32_t NS = currentTime.getNanosecond();

        cote::Satellite* bestSat = nullptr;
        int    bestBinCount = std::numeric_limits<int>::max();
        double bestDownloadTime = std::numeric_limits<double>::infinity();
        double bestFresh = -1.0;

        for (const auto* sat : visibleSats) {
            const uint32_t SAT_ID = sat->getID();
            const uint64_t BUF = satId2Sensor.at(SAT_ID)->getBitsBuffered();

            if (BUF == 0) continue;
            if (satId2Occupied.count(SAT_ID) && satId2Occupied.at(SAT_ID)) continue;
            if (!satId2ImageQueue.count(SAT_ID)) continue;
            const auto& queue = satId2ImageQueue.at(SAT_ID);
            if (queue.empty()) continue;

            double bitrateMbps = 0.0;
            if (satId2BitrateMbps.count(SAT_ID)) {
                bitrateMbps = satId2BitrateMbps.at(SAT_ID);
            }
            double bitrateBps = bitrateMbps * 1.0e6;

            double remainingSec = 0.0;
            if (groundStation != nullptr) {
                remainingSec = estimateRemainingPassSeconds(
                    sat, groundStation, JD, SEC, NS
                );
            }

            bool useFeasibility = (bitrateBps > 0.0 && remainingSec > 0.0);

            // Find this satellite's best candidate image
            int    satBinCount = std::numeric_limits<int>::max();
            double satDownloadTime = std::numeric_limits<double>::infinity();
            double satFresh = -1.0;
            bool   satHasViable = false;

            for (const auto& img : queue) {
                if (useFeasibility &&
                    !canCompleteDownload(img, bitrateBps, remainingSec)) {
                    continue;
                }

                int bc = getBinCount(img);
                double dlTime = computeDownloadTimeSec(img, bitrateBps);
                double fresh = parseTimestampToSeconds(img.timestamp);

                if (!satHasViable) {
                    satBinCount = bc;
                    satDownloadTime = dlTime;
                    satFresh = fresh;
                    satHasViable = true;
                } else if (bc < satBinCount) {
                    satBinCount = bc;
                    satDownloadTime = dlTime;
                    satFresh = fresh;
                } else if (bc == satBinCount) {
                    if (dlTime < satDownloadTime) {
                        satDownloadTime = dlTime;
                        satFresh = fresh;
                    } else if (std::abs(dlTime - satDownloadTime) < 1e-6) {
                        if (fresh > satFresh) {
                            satFresh = fresh;
                        }
                    }
                }
            }

            if (!satHasViable) continue;

            bool isBetter = false;
            if (satBinCount < bestBinCount) {
                isBetter = true;
            } else if (satBinCount == bestBinCount) {
                if (satDownloadTime < bestDownloadTime) {
                    isBetter = true;
                } else if (std::abs(satDownloadTime - bestDownloadTime) < 1e-6) {
                    if (satFresh > bestFresh) {
                        isBetter = true;
                    }
                }
            }

            if (isBetter) {
                bestBinCount = satBinCount;
                bestDownloadTime = satDownloadTime;
                bestFresh = satFresh;
                bestSat = const_cast<cote::Satellite*>(sat);
            }
        }

        return bestSat;
    }

    // Legacy 7-parameter interface
    cote::Satellite* makeSchedulingDecision(
        const std::vector<cote::Satellite*>& visibleSats,
        const std::map<uint32_t, cote::Sensor*>& satId2Sensor,
        const std::map<uint32_t, bool>& satId2Occupied,
        const cote::DateTime& currentTime,
        uint32_t groundStationId,
        cote::Satellite* currentSat,
        uint64_t stepCount
    ) override {
        return nullptr;
    }
};
