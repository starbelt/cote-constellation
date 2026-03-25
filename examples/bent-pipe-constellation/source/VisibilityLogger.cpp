// VisibilityLogger.cpp
//
// Minimal utility for visibility logging
//
// Written by GitHub Copilot
// Other contributors: None
//
// See the top-level LICENSE file for the license.

#include "VisibilityLogger.hpp"
#include <iomanip>

VisibilityLogger::VisibilityLogger(const std::filesystem::path& logDirectory) {
  std::filesystem::path visibilityLogPath = logDirectory / "visibility_log.csv";
  visibilityLog.open(visibilityLogPath.string());
  visibilityLog << "time,sat_id,in_view,connected,buffer_mb,downloaded_mb,image_taken,lat_deg,lon_deg,freshness_timestamp,distance_km,elevation_deg,decision_interval,bitrate_mbps,image_completed,completed_image_lat,completed_image_lon,completed_image_timestamp,downloaded_image_lat,downloaded_image_lon\n";
}

VisibilityLogger::~VisibilityLogger() {
  close();
}

void VisibilityLogger::writeEntry(
    double simTimeSeconds,
    uint32_t SAT_ID,
    int inView,
    int connected,
    double bufferMB,
    double downloadedMB,
    int imageTaken,
    double latDeg,
    double lonDeg,
    const std::string& timestamp,
    double distanceKm,
    double elevationDeg,
    uint32_t decisionInterval,
    double bitrateMbps,
    int imageCompleted,
    double completedImageLat,
    double completedImageLon,
    const std::string& completedImageTimestamp,
    double downloadedImageLat,
    double downloadedImageLon
) {
  visibilityLog << simTimeSeconds << ","
               << SAT_ID << ","
               << inView << ","
               << connected << ","
               << std::fixed << std::setprecision(6) << bufferMB << ","
               << std::fixed << std::setprecision(6) << downloadedMB << ","
               << imageTaken << ","
               << std::fixed << std::setprecision(6) << latDeg << ","
               << std::fixed << std::setprecision(6) << lonDeg << ","
               << timestamp << ","
               << std::fixed << std::setprecision(3) << distanceKm << ","
               << std::fixed << std::setprecision(2) << elevationDeg << ","
               << decisionInterval << ","
               << std::fixed << std::setprecision(3) << bitrateMbps << ","
               << imageCompleted << ","
               << std::fixed << std::setprecision(6) << completedImageLat << ","
               << std::fixed << std::setprecision(6) << completedImageLon << ","
               << completedImageTimestamp << ","
               << std::fixed << std::setprecision(6) << downloadedImageLat << ","
               << std::fixed << std::setprecision(6) << downloadedImageLon << "\n";
}

void VisibilityLogger::close() {
  if(visibilityLog.is_open()) {
    visibilityLog.close();
  }
}
