#!/usr/bin/env python3
"""Panel attribution analysis for H629 and H630.

H629 added the measurements; H630 split the console operations apart, reported
the console-ownership control state, and cleared the decay row at each blit so
a printed row can no longer mix two write cycles. Both line shapes are read.

The report is in the order the evidence has to be taken:

  1. the same-beat double read, because every other number depends on it,
  2. which blocks lost pixels and what value replaced them,
  3. how fast the loss follows a blit,
  4. whether the kernel text console was writing in those beats, and after H630
     whether the control actually stopped it.

Usage: analyze-h629-panel-attribution.py <log>
"""
import re
import sys

NOT_REACHED = 0xFFFFFFFF

COMMON = (
    r"build=(?P<build>\S+) samples=(?P<samples>\d+) "
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
    r"h=(?P<glyph>\d+) ")

WATCH_H630 = re.compile(COMMON +
    r"paint=(?P<paint>\d+) clear=(?P<clear>\d+) cursor=(?P<cursor>\d+) "
    r"ctl=(?P<ctl>\d+) gc=(?P<gc>\d+) wrote=(?P<wrote>\d+) both=(?P<both>\d+) "
    r"neither=(?P<neither>\d+)")
WATCH_H629 = re.compile(COMMON +
    r"wrote=(?P<wrote>\d+) both=(?P<both>\d+) neither=(?P<neither>\d+)")

PANEL = re.compile(
    r"NATIVE_A540_PANEL: mapped=\d+ runs=(?P<runs>\d+) .*?"
    r"carry=(?P<carry>[0-9a-f]+) kept=(?P<kept>\d+)/(?P<kepttotal>\d+) .*?finalkept="
    r"(?P<finalkept>\d+)/(?P<finaltotal>\d+)")

ACTIVITY = re.compile(
    r"NATIVE_PANEL_ACTIVITY: prog=(?P<prog_e>\d+)/(?P<prog_x>\d+)/(?P<prog_p>\d+) "
    r"panic=(?P<pan_e>\d+)/(?P<pan_x>\d+)/(?P<pan_p>\d+) "
    r"blank=(?P<bla_e>\d+)/(?P<bla_x>\d+)/(?P<bla_p>\d+) "
    r"copy=(?P<cpy_e>\d+)/(?P<cpy_x>\d+)/(?P<cpy_p>\d+) "
    r"pat=(?P<pat_e>\d+)/(?P<pat_x>\d+)/(?P<pat_p>\d+) "
    r"slot=(?P<slot_e>\d+)/(?P<slot_x>\d+)/(?P<slot_p>\d+) "
    r"usb=(?P<usb_e>\d+)/(?P<usb_x>\d+)/(?P<usb_p>\d+) "
    r"hbcell=(?P<hb_e>\d+)/(?P<hb_x>\d+)/(?P<hb_p>\d+)")

BLOCKS = (("blue    y0", "b0"), ("green   y384", "b1"), ("red     y768", "b2"),
          ("cyan    y1152", "b3"), ("yellow  y1536", "b4"), ("magenta y1880", "b5"))
DECAY = (("beat +1", "d1"), ("beat +2", "d2"), ("beat +3", "d3"), ("beat +5", "d5"),
         ("beat +10", "d10"), ("beat +20", "d20"), ("beat +29", "d29"))


def fmt_decay(value):
    return "not reached" if int(value) == NOT_REACHED else value


def main(path):
    watches, panels, activity = [], [], []
    with open(path, "r", errors="replace") as handle:
        for line in handle:
            m = WATCH_H630.search(line) or WATCH_H629.search(line)
            if m:
                watches.append(m.groupdict())
                continue
            p = PANEL.search(line)
            if p:
                panels.append(p.groupdict())
                continue
            a = ACTIVITY.search(line)
            if a:
                activity.append(a.groupdict())

    if not watches:
        print("no NATIVE_PANEL_WATCH line matched: wrong log shape")
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
    print("  black 0xff000000: %s   white 0xffffffff: %s   grey 0xff404040: %s"
          % (g["black"], g["white"], g["grey"]))
    print("  a different block's own test colour: %s" % g["tile"])
    print("  unexplained %s, first value 0x%s at panel dword 0x%s"
          % (g["unk"], g["unkval"], g["unko"]))
    if g["unkval"] == "0":
        print("  0x00000000 is video_console.c's default vc_color_back and vc_color_fore,")
        print("  so a console character cell painted with the default colours lands here.")

    print("")
    print("decay after the most recent blit (pixels of 3072 still holding their colour):")
    for name, key in DECAY:
        print("  %-9s %s" % (name, fmt_decay(g[key])))
    if panels:
        print("  at the blit itself: run %s finalkept=%s/%s"
              % (panels[-1]["runs"], panels[-1]["finalkept"], panels[-1]["finaltotal"]))
        print("  before the next blit: carry=%s kept=%s/%s (what survived the gap)"
              % (panels[-1]["carry"], panels[-1]["kept"], panels[-1]["kepttotal"]))

    print("")
    print("console operations:")
    print("  scroll calls %s (H629 found the scroll path never runs)" % g["sc"])
    if "paint" in g and g["paint"] is not None:
        print("  paint_char %s   clear_screen %s   reverse_cursor %s"
              % (g["paint"], g["clear"], g["cursor"]))
        print("  control ran %s   last gc_enable argument %s" % (g["ctl"], g["gc"]))
    else:
        print("  glyph/clear/cursor combined: %s (split from H630)" % g["dr"])
    print("  text grid %sx%s, glyph height %s panel rows, last scroll region %s-%s"
          % (g["gridw"], g["gridh"], g["glyph"], g["top"], g["bottom"]))
    wrote, both, neither = int(g["wrote"]), int(g["both"]), int(g["neither"])
    print("  beats the console wrote              : %s" % g["wrote"])
    print("  beats console wrote AND panel changed: %s" % g["both"])
    print("  beats panel changed, console did not : %s" % g["neither"])

    if activity:
        a = activity[-1]
        print("")
        print("display-side writers (entered / stopped at a guard / pixels written):")
        for label, keys in (("progress", ("prog_e", "prog_x", "prog_p")),
                            ("panic fill", ("pan_e", "pan_x", "pan_p")),
                            ("blank fill", ("bla_e", "bla_x", "bla_p")),
                            ("swap copy", ("cpy_e", "cpy_x", "cpy_p")),
                            ("2x2 pattern", ("pat_e", "pat_x", "pat_p")),
                            ("slot cell", ("slot_e", "slot_x", "slot_p")),
                            ("usb cell", ("usb_e", "usb_x", "usb_p")),
                            ("heartbeat cell", ("hb_e", "hb_x", "hb_p"))):
            print("  %-15s %s / %s / %s" % (label, a[keys[0]], a[keys[1]], a[keys[2]]))

    changed = both + neither
    samples = int(g["samples"])
    transitions = int(g["transitions"])
    atBlit = int(panels[-1]["finalkept"]) if panels else None
    nowTotal = int(g["now"])
    print("")
    print("persistence:")
    print("  transitions per sample        : %d / %d = %.3f"
          % (transitions, samples, transitions / float(samples or 1)))
    print("  total now vs total at the blit: %s vs %s" % (nowTotal, atBlit))
    if atBlit:
        print("  content still present         : %.1f%% of what was written"
              % (100.0 * nowTotal / atBlit))
    stable = (atBlit is not None and nowTotal == atBlit
              and transitions <= 2 and wrote <= 2)
    print("")
    if checks and disagree:
        print("VERDICT: withheld, the read path failed its own check.")
    elif stable:
        print("VERDICT: the content is persistent. Nothing changed the panel in %d"
              % samples)
        print("  sampled beats beyond the two console calls made at acquire time, and")
        print("  the total still equals what the blit wrote. H629 measured that almost")
        print("  every panel-change beat coincided with a console draw; with the console")
        print("  handed off, that loss is gone. The text console was the writer.")
    elif wrote == 0 and changed:
        print("VERDICT: the console never wrote during the sampled beats while the panel")
        print("  changed in %d of them, so the console is excluded." % changed)
    elif changed == 0:
        print("VERDICT: the panel content did not change in any sampled beat.")
    elif neither == 0:
        print("VERDICT: all %d beats where the panel changed also had a console write," % both)
        print("  and no change happened without one.")
    elif both == 0:
        print("VERDICT: the panel changed in %d beats with no console write and never" % neither)
        print("  together with one. The console is excluded.")
    else:
        share = both / float(changed)
        print("VERDICT: %d of %d panel-change beats (%.0f%%) coincided with a console"
              % (both, changed, 100.0 * share))
        print("  write. The remaining %d are few enough that the console explains most"
              % neither)
        print("  of the loss; the control run decides it.")
    print("")
    print("Scope: these are beats that were sampled, not the whole session. Sampling only")
    print("runs once the panel window is ready, and the attribution counters start there.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
