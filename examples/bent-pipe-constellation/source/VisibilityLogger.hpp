#ifndef VISIBILITY_LOGGER_HPP
#define VISIBILITY_LOGGER_HPP

#include <filesystem>
#include <fstream>
#include <string>
#include <map>
#include <cstdint>

class VisibilityLogger {
public:
  VisibilityLogger(const std::filesystem::path& logDirectory);
  ~VisibilityLogger();
  
  // Write a log entry
  void writeEntry(
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
  );
  
  void close();

private:
  std::ofstream visibilityLog;
};

#endif // VISIBILITY_LOGGER_HPP
