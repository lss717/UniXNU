#!/usr/bin/env python3
"""Resolve user addresses against an iOS dyld shared cache.

The sampler in the kernel prints raw user addresses (pc, lr and the frame chain).
Turning them into "image + offset" needs the dyld shared cache of the *same*
IPSW, because the cache is where every system library is mapped from.

Usage:

    # The cache directory of the mounted SystemOS volume:
    #   /System/Library/Caches/com.apple.dyld
    # --slide is the value the sampler prints (NATIVE_SBPC_IMAGE slide=0x...).
    scripts/h103-symbolicate.py --cache /tmp/dsc/System/Library/Caches/com.apple.dyld \
        --slide 0x14f28000 0x1e06ac1b0 0x1a4584cac

Addresses may also be read from a log on stdin ("--from-log"): every
NATIVE_SBPC pc/lr and NATIVE_SBFRAME lr value is resolved.

The cache is a set of files (dyld_shared_cache_arm64, .01, .02, ...).  Each has
its own header with a mapping table (address, size, file offset) and an image
list (load address, path), so a slid address becomes

    unslid = address - slide
    image  = the image with the largest load address <= unslid

which is exactly what the kernel could not print.
"""

import argparse
import glob
import os
import re
import struct
import sys

PAGE = 0x4000

# dyld_cache_header field offsets (stable since the cache was introduced).
HDR_MAPPING_OFFSET = 0x10       # uint32
HDR_MAPPING_COUNT = 0x14        # uint32
HDR_IMAGES_OFFSET = 0x18        # uint32   (dyld_cache_image_info array)
HDR_IMAGES_COUNT = 0x1c         # uint32
HDR_IMAGES_TEXT_OFFSET = 0x88   # uint64   (dyld_cache_image_text_info array)
HDR_IMAGES_TEXT_COUNT = 0x90    # uint64

MAPPING_SIZE = 32               # {u64 address, u64 size, u64 fileOffset, u32 maxProt, u32 initProt}
IMAGE_INFO_SIZE = 32            # {u64 address, u64 modTime, u64 inode, u32 pathOffset, u32 pad}
IMAGE_TEXT_SIZE = 32            # {u8 uuid[16], u64 loadAddress, u32 textSegmentSize, u32 pathOffset}


def read_at(path, offset, size):
    with open(path, "rb") as handle:
        handle.seek(offset)
        data = handle.read(size)
    if len(data) != size:
        raise IOError("%s: short read at 0x%x" % (path, offset))
    return data


def load_cache(directory):
    """Return (mappings, images) for every cache file in the directory."""
    mappings = []
    images = []
    files = sorted(glob.glob(os.path.join(directory, "dyld_shared_cache_arm64*")))
    for path in files:
        if path.endswith(".symbols") or path.endswith(".map"):
            continue
        try:
            header = read_at(path, 0, 0x200)
        except (IOError, OSError):
            continue
        if header[:4] != b"dyld":
            continue
        mapping_offset, mapping_count = struct.unpack_from("<II", header, HDR_MAPPING_OFFSET)
        if 0 < mapping_count < 64:
            table = read_at(path, mapping_offset, MAPPING_SIZE * mapping_count)
            for index in range(mapping_count):
                address, size, file_offset, _max, _init = struct.unpack_from(
                    "<QQQII", table, index * MAPPING_SIZE)
                if size:
                    mappings.append((address, size, file_offset, os.path.basename(path)))
        images_offset, images_count = struct.unpack_from("<II", header, HDR_IMAGES_OFFSET)
        if 0 < images_count < 200000:
            table = read_at(path, images_offset, IMAGE_INFO_SIZE * images_count)
            for index in range(images_count):
                address, _mtime, _inode, path_offset, _pad = struct.unpack_from(
                    "<QQQII", table, index * IMAGE_INFO_SIZE)
                name = read_at(path, path_offset, 512).split(b"\0")[0]
                if name:
                    images.append((address, name.decode("utf-8", "replace")))
        text_offset, text_count = struct.unpack_from("<QQ", header, HDR_IMAGES_TEXT_OFFSET)
        if 0 < text_count < 200000:
            table = read_at(path, text_offset, IMAGE_TEXT_SIZE * text_count)
            for index in range(text_count):
                load, _size, path_offset = struct.unpack_from(
                    "<QII", table, index * IMAGE_TEXT_SIZE + 16)
                name = read_at(path, path_offset, 512).split(b"\0")[0]
                if name:
                    images.append((load, name.decode("utf-8", "replace")))
    images.sort()
    return mappings, images


def describe(mappings, images, address, slide):
    unslid = address - slide
    image = None
    for load, name in images:
        if load <= unslid:
            image = (load, name)
        else:
            break
    if image is None:
        return "0x%x -> 0x%x no image (outside the shared cache)" % (address, unslid)
    mapping = None
    for base, size, _file_offset, owner in mappings:
        if base <= unslid < base + size:
            mapping = owner
            break
    return "0x%x -> 0x%x %s +0x%x%s" % (
        address, unslid, image[1], unslid - image[0],
        "" if mapping is None else " [%s]" % mapping)


def addresses_from_log(stream):
    pattern = re.compile(r"(?:pc|lr)=(0x[0-9a-f]+)")
    seen = []
    for line in stream:
        for match in pattern.finditer(line):
            value = int(match.group(1), 16)
            if value not in seen:
                seen.append(value)
    return seen


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cache", required=True, help="directory holding dyld_shared_cache_arm64*")
    parser.add_argument("--slide", default="0", help="shared region slide printed by the sampler")
    parser.add_argument("--from-log", action="store_true", help="read addresses from stdin")
    parser.add_argument("addresses", nargs="*", help="user addresses, hex")
    options = parser.parse_args()

    slide = int(options.slide, 0) if options.slide.startswith("0x") else int(options.slide, 16)
    mappings, images = load_cache(options.cache)
    if not images:
        sys.exit("%s: no dyld shared cache found" % options.cache)

    addresses = [int(value, 16) for value in options.addresses]
    if options.from_log:
        addresses = addresses_from_log(sys.stdin)
    if not addresses:
        sys.exit("no addresses given")

    for address in addresses:
        print(describe(mappings, images, address, slide))


if __name__ == "__main__":
    main()
