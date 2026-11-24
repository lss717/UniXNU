#!/usr/bin/env python3
"""Replay the a5xx panel blit command stream on the host, without a device.

Regenerates the exact indirect-buffer words that
native_a540_hb_panel_selftest() step B builds for each rectangle row, so a
wrong address, a wrong shift, a field that overflows its 16 bits, or a
difference between two rows can be found by reading numbers instead of
spending a boot. The register layout is taken from the Mesa and Linux kernel
copies of adreno/a5xx.xml:

    0x2107 RB_2D_SRC_INFO   0x2108 RB_2D_SRC_LO   0x2109 RB_2D_SRC_HI
    0x210a RB_2D_SRC_SIZE   (PITCH shr 6 | ARRAY_PITCH shr 6 << 16)
    0x2110 RB_2D_DST_INFO   0x2111 RB_2D_DST_LO   0x2112 RB_2D_DST_HI
    0x2113 RB_2D_DST_SIZE   (same field split)

Usage: a5xx-panel-blit-dump.py [--row ROW] [--block BLOCK]
"""
import argparse

# --- packet builders, mirroring NativeA540C3.cpp ---------------------------
def parity(value):
    value ^= value >> 16
    value ^= value >> 8
    value ^= value >> 4
    value ^= value >> 2
    value ^= value >> 1
    return (~value) & 1


def type4(addr, count):
    return (0x40000000 | (count & 0x7F) | (parity(count) << 7)
            | ((addr & 0x3FFFF) << 8) | (parity(addr) << 27)) & 0xFFFFFFFF


def type7(opcode, count):
    return (0x70000000 | (count & 0x3FFF) | (parity(count) << 15)
            | ((opcode & 0x7F) << 16) | (parity(opcode) << 23)) & 0xFFFFFFFF


CP_SET_RENDER_MODE = 0x6C
CP_BLIT = 0x2C
RENDER_BLIT_2D = 5
RENDER_END_2D = 8
RB_2D_SRC_INFO = 0x2107
RB_2D_DST_INFO = 0x2110
GRAS_2D_SRC_INFO = 0x2181
GRAS_2D_DST_INFO = 0x2182
SURF_RGBA8_LINEAR = 0x30
BLIT_OP_COPY = 1

PANEL_IOVA = 0x4000000
SURF_DST_IOVA = 0x3100000
PANEL_ROW_BYTES = 4320          # what PE_current_console reports for the panel
SURF_ROW_BYTES = 4352           # the surface plane 0 row stride
RECT_X = 480
RECT_Y = [0, 384, 768, 1152, 1536, 1880]
TILE_Y = [16, 32, 48, 64, 80, 96]
PAT_WIDTH = 64
PAT_HEIGHT = 8
PANEL_WIDTH = 1080
PANEL_HEIGHT = 1920
PANEL_BYTES = 0x7E9000
SETUP = [(0xE141, 0x00000008), (0x2100, 0x86000000), (0x2180, 0x86000000),
         (0x2184, 0x00000009), (0xE140, 0x00020000), (0x0CC6, 0x00000004),
         (0x0EC2, 0x0000000C), (0x0F02, 0x00000344), (0x0E06, 0x00000002),
         (0xE000, 0x00000181)]


def row_commands(block, row_in_block):
    """The 34 words one panel row's blit contributes, plus its geometry."""
    panel_row = RECT_Y[block] + row_in_block
    dst_byte = PANEL_IOVA + panel_row * PANEL_ROW_BYTES + RECT_X * 4
    dst_aligned = dst_byte & ~63
    shift = (dst_byte - dst_aligned) // 4
    src_row = TILE_Y[block] + row_in_block
    words = []
    words.append(type7(CP_SET_RENDER_MODE, 1)); words.append(RENDER_BLIT_2D)
    words.append(type4(RB_2D_SRC_INFO, 9))
    words.append(SURF_RGBA8_LINEAR)
    words.append(SURF_DST_IOVA & 0xFFFFFFFF)
    words.append(SURF_DST_IOVA >> 32)
    words.append((SURF_ROW_BYTES >> 6) | ((SURF_ROW_BYTES >> 6) << 16))
    words += [0] * 5
    words.append(type4(GRAS_2D_SRC_INFO, 1)); words.append(SURF_RGBA8_LINEAR)
    words.append(type4(RB_2D_DST_INFO, 9))
    words.append(SURF_RGBA8_LINEAR)
    words.append(dst_aligned & 0xFFFFFFFF)
    words.append(dst_aligned >> 32)
    words.append((SURF_ROW_BYTES >> 6) | ((64 >> 6) << 16))
    words += [0] * 5
    words.append(type4(GRAS_2D_DST_INFO, 1)); words.append(SURF_RGBA8_LINEAR)
    words.append(type7(CP_BLIT, 5))
    words.append(BLIT_OP_COPY)
    words.append(16 | (src_row << 16))                       # SRC_X1, SRC_Y1
    words.append((16 + PAT_WIDTH - 1) | (src_row << 16))     # SRC_X2, SRC_Y2
    words.append(shift)                                      # DST_X1, DST_Y1
    words.append(shift + PAT_WIDTH - 1)                      # DST_X2, DST_Y2
    words.append(type7(CP_SET_RENDER_MODE, 1)); words.append(RENDER_END_2D)
    geometry = {
        "panel_row": panel_row, "src_row": src_row,
        "dst_byte": dst_byte, "dst_aligned": dst_aligned,
        "shift": shift, "dst_pitch_field": (SURF_ROW_BYTES >> 6),
        "dst_array_pitch_bytes": 64,
        "words": len(words),
    }
    return words, geometry


def check(geometry):
    """Host-side invariants that would otherwise only show up on the device."""
    problems = []
    g = geometry
    if g["dst_byte"] % 4:
        problems.append("destination byte address is not 4-byte aligned")
    if g["dst_byte"] + PAT_WIDTH * 4 > PANEL_IOVA + PANEL_BYTES:
        problems.append("destination row runs past the panel buffer")
    offset = g["dst_byte"] - PANEL_IOVA
    if g["panel_row"] >= PANEL_HEIGHT:
        problems.append("destination row is past the last panel row")
    if offset != g["panel_row"] * PANEL_ROW_BYTES + RECT_X * 4:
        problems.append("destination offset does not match the panel row")
    if (offset + PAT_WIDTH * 4) > PANEL_BYTES:
        problems.append("destination row runs past the panel buffer length")
    if g["shift"] + PAT_WIDTH > SURF_ROW_BYTES // 4:
        problems.append("destination x range exceeds the declared dst pitch")
    if 16 + PAT_WIDTH - 1 > SURF_ROW_BYTES // 4:
        problems.append("source x range exceeds the declared src pitch")
    if g["dst_pitch_field"] * 64 != SURF_ROW_BYTES:
        problems.append("dst pitch field cannot represent the stride exactly")
    if PANEL_BYTES < PANEL_ROW_BYTES * PANEL_HEIGHT:
        problems.append("panel buffer 0x%x is %d bytes shorter than rowBytes x "
                        "height = %d, which bounds the full-screen stage"
                        % (PANEL_BYTES, PANEL_ROW_BYTES * PANEL_HEIGHT - PANEL_BYTES,
                           PANEL_ROW_BYTES * PANEL_HEIGHT))
    if PANEL_ROW_BYTES % 64:
        problems.append("panel row bytes %d is not a multiple of 64, so the "
                        "pitch field cannot express the real panel stride "
                        "(%d/64 = %s)" % (PANEL_ROW_BYTES, PANEL_ROW_BYTES,
                                          PANEL_ROW_BYTES / 64))
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--block", type=int, default=None)
    ap.add_argument("--row", type=int, default=None)
    args = ap.parse_args()
    blocks = [args.block] if args.block is not None else range(6)
    all_problems = set()
    for b in blocks:
        rows = [args.row] if args.row is not None else range(PAT_HEIGHT)
        for r in rows:
            words, g = row_commands(b, r)
            all_problems.update(check(g))
            print("block %d row %d: panel_row=%d src_row=%d "
                  "dst_byte=0x%07x dst_aligned=0x%07x shift=%d "
                  "dst_x=%d..%d src_x=16..%d words=%d"
                  % (b, r, g["panel_row"], g["src_row"], g["dst_byte"],
                     g["dst_aligned"], g["shift"], g["shift"],
                     g["shift"] + PAT_WIDTH - 1, 16 + PAT_WIDTH - 1,
                     g["words"]))
            if args.row is not None or args.block is not None:
                print("   " + " ".join("%08x" % w for w in words))
    print("")
    for p in sorted(all_problems):
        print("INVARIANT: " + p)


if __name__ == "__main__":
    main()
