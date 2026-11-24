#!/usr/bin/env python3
"""H629 panel attribution analysis.

Reads a decoded H629 kernel log and reports the four measurements that round
added, in the order they have to be read:

  1. whether the read path can be trusted at all (the same-beat double read),
  2. which blocks lose pixels and where the replacement values came from,
  3. how fast the content goes after a blit (the decay curve),
  4. whether the kernel text console was writing in the beats the panel changed.

A run whose double-read check disagrees is reported as unusable, because every
other number here depends on that read.

Usage: analyze-h629-panel-attribution.py <log>
"""
import re
import sys

WATCH = re.compile(
    r"NATIVE_PANEL_WATCH: build=(?P<build>\S+) samples=(?P<samples>\d+) "
    r"now=(?P<now>\d+) mask=(?P<mask>[0-9a-f]+) transitions=(?P<transitions>\d+) "
    r"prev=(?P<prev>\d+) atSample=(?P<atsample>\d+) "
    r"blocks=(?P<b0>\d+)/(?P<b1>\d+)/(?P<b2>\d+)/(?P<b3>\d+)/(?P<b4>\d+)/(?P<b5>\d+) "
    r"sig blk=(?P<black>\d+) wht=(?P<white>\d+) gry=(?P<grey>\d+) "
    r"tile=(?P<tile>\d+) unk=(?P<unk>\d+) unkval=(?P<unkval>[0-9a-f]+) "
    r"unko=(?P<unko>[0-9a-f]+) "
    r"decay=(?P<d1>\d+)/(?P<d2>\d+)/(?P<d3>\d+)/(?P<d5>\d+)/(?P<d10>\d+)/"
    r"(?P<d20>\d+)/(?P<d29>\d+) "
    r"reread=(?P<disagree>\d+)/(?P<checks>\d+) "
    r"cons sc=(?P<sc>\d+) dr=(?P<dr>\d+) rows=(?P<rows>\d+) "
    r"region=(?P<top>\d+)-(?P<bottom>\d+) grid=(?P<gridw>\d+)x(?P<gridh>\d+) "
    r"h=(?P<glyph>\d+) wrote=(?P<wrote>\d+) both=(?P<both>\d+) "
    r"neither=(?P<neither>\d+)")

PANEL = re.compile(
    r"NATIVE_A540_PANEL: mapped=\d+ runs=(?P<runs>\d+) .*?finalkept="
    r"(?P<finalkept>\d+)/(?P<finaltotal>\d+)")

BLOCKS = (("blue    y0", "b0"), ("green   y384", "b1"), ("red     y768", "b2"),
          ("cyan    y1152", "b3"), ("yellow  y1536", "b4"), ("magenta y1880", "b5"))
DECAY = (("beat +1", "d1"), ("beat +2", "d2"), ("beat +3", "d3"), ("beat +5", "d5"),
         ("beat +10", "d10"), ("beat +20", "d20"), ("beat +29", "d29"))


def main(path):
    watches, panels = [], []
    with open(path, "r", errors="replace") as handle:
        for line in handle:
            m = WATCH.search(line)
            if m:
                watches.append(m.groupdict())
                continue
            p = PANEL.search(line)
            if p:
                panels.append(p.groupdict())

    if not watches:
        print("no NATIVE_PANEL_WATCH lines: this log is not from H629 or later")
        return 1

    g = watches[-1]
    disagree, checks = int(g["disagree"]), int(g["checks"])
    print("build tag          : %s (%d watch samples)" % (g["build"], int(g["samples"])))
    print("read self-check    : %d disagreements in %d probe reads" % (disagree, checks))
    if checks and disagree:
        print("  UNUSABLE: the same-beat double read disagrees, so the panel window is")
        print("  not a reliable view of what is being scanned. Fix the read path before")
        print("  believing anything below.")
    elif checks:
        print("  the panel window reads consistently inside one beat")
    else:
        print("  NOT CHECKED: no double read ran, so the read path is unverified")

    print("")
    print("last sample per block (of 512 each), mask=%s means %s blocks fully intact"
          % (g["mask"], bin(int(g["mask"], 16)).count("1")))
    for name, key in BLOCKS:
        print("  %-13s %s" % (name, g[key]))
    print("  total still holding its own colour: %s of 3072" % g["now"])

    print("")
    print("replacement signature in that sample:")
    print("  black %s   white %s   diagnostic grey %s" % (g["black"], g["white"], g["grey"]))
    print("  a different block's own test colour: %s" % g["tile"])
    print("  unexplained %s, first value 0x%s at panel dword 0x%s"
          % (g["unk"], g["unkval"], g["unko"]))

    print("")
    print("decay after the most recent blit (pixels of 3072 still holding their colour):")
    for name, key in DECAY:
        print("  %-9s %s" % (name, g[key]))
    if panels:
        print("  at the blit itself: run %s finalkept=%s/%s"
              % (panels[-1]["runs"], panels[-1]["finalkept"], panels[-1]["finaltotal"]))

    print("")
    print("console attribution:")
    print("  scroll calls %s, glyph/clear/cursor calls %s" % (g["sc"], g["dr"]))
    print("  text grid %sx%s, glyph height %s panel rows, last scroll region %s-%s"
          % (g["gridw"], g["gridh"], g["glyph"], g["top"], g["bottom"]))
    wrote, both, neither = int(g["wrote"]), int(g["both"]), int(g["neither"])
    print("  beats the console wrote              : %s" % g["wrote"])
    print("  beats console wrote AND panel changed: %s" % g["both"])
    print("  beats panel changed, console did not : %s" % g["neither"])

    changed = both + neither
    print("")
    if checks and disagree:
        print("VERDICT: withheld, the read path failed its own check.")
    elif wrote == 0:
        print("VERDICT: the console never wrote during the sampled beats, so it is not the")
        print("  writer and the search continues elsewhere.")
    elif changed == 0:
        print("VERDICT: the panel content did not change in any sampled beat, so this run")
        print("  says nothing about who caused the earlier loss.")
    elif neither == 0:
        print("VERDICT: all %d beats where the panel changed also had a console write, and"
              % both)
        print("  no change happened without one. The console accounts for every observed")
        print("  change in this run.")
    elif both == 0:
        print("VERDICT: the panel changed in %d beats where the console did not write and"
              % neither)
        print("  never together with it. The console is excluded for those changes.")
    else:
        print("VERDICT: mixed. %d beats match a console write, %d do not, so the console is"
              % (both, neither))
        print("  a writer but not the only one.")
    print("")
    print("Scope: these are beats that were sampled, not the whole session. Sampling only")
    print("runs once the panel window is ready, and the attribution counters start there.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
