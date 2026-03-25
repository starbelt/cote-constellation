#ifndef IMAGE_METADATA_HPP
#define IMAGE_METADATA_HPP

#include <cstdint>
#include <string>

struct ImageMetadata {
  double captureLat;
  double captureLon;
  std::string timestamp;
  uint64_t sizeBits;
  uint64_t originalSizeBits;
};

#endif // IMAGE_METADATA_HPP
