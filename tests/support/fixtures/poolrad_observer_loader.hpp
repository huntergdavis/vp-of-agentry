// Verbatim observer prefix through load(); only the closing namespace/guard are appended.
// Source: huntergdavis/poolrad-decomp @ ceb665018d911d61891e7f39df778a5e6de1a020
// tools/hybrid/dosbox-x-5a9c7c53-dispatch.patch, src/cpu/pr_hybrid_observer.h
// Full extracted header SHA-256: d941dc54ff83313ee76cd10d56b8fb788af5aaf2f63c2f0a071f3ca5cf4b6531
/* Poolrad hybrid executor, STAGE 0: OBSERVER ONLY (docs/HYBRID_EXECUTOR_SCOPE.md in the poolrad-decomp repo, VP i20556).
 *
 * Counts arrivals at credited entry points. It never changes guest state: it reads guest bytes and writes host files.
 * Inactive unless PR_HYBRID_REGISTRY names a registry (tools/hybrid/hybrid_registry.py output). An arrival is an
 * instruction start, in real mode, whose IP equals a registry entry's offset and whose bytes at CS:IP equal that entry's
 * signature with relocated words masked. Only signatures unique across all game code are used; the rest are listed as
 * unobservable in the report.
 *
 * Output (PR_HYBRID_LOG, default pr_hybrid_observer): <log>.tsv (per-ID counts, first arrival) rewritten every 4096
 * arrivals and at exit, and <log>.seq (every arrival in order, capped at SEQ_CAP lines; the cap is reported). */
#ifndef PR_HYBRID_OBSERVER_H
#define PR_HYBRID_OBSERVER_H
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <string>
#include <vector>
#include <sys/time.h>
#include <sys/stat.h>

namespace pr_obs {
struct Entry {
    std::string id;
    uint16_t ip;
    std::vector<uint8_t> sig, mask;
    uint64_t count, first_insn;
    uint16_t first_cs;
};
static int state = 0;                         /* 0 not loaded, 1 inactive, 2 active */
static std::vector<Entry> entries;
static std::vector<std::string> skipped;      /* registry rows whose signature is not unique */
static std::vector<std::vector<int> > by_ip;  /* IP -> indexes into entries */
static std::vector<uint8_t> hit;              /* IP -> nonzero when some entry has this IP */
static uint64_t insns = 0, arrivals = 0, seq_lines = 0;
static const uint64_t SEQ_CAP = 2000000;
static std::string log_base;
static FILE *seq = NULL;
static FILE *draws = NULL;
/* Seed-pin stage 2 (PM i22231): a TEST-HARNESS POKE, off unless PR_HYBRID_SEED_PIN is set. At the first RandSeed step (a DRAW_ row) after the
 * driver has created <log>.pin (it does so at SAVE LOADED), DS:4428..442B := PR_HYBRID_SEED_PIN before the step runs. Logged in <log>.draws. */
static int pin_state = 0;                     /* 0 off, 1 armed, 2 done */
static uint32_t pin_value = 0;                    /* <log>.draws: every arrival of a DRAW_ row (the RandSeed step), never capped */
static void (*on_match)(int index, uint16_t cs, uint16_t ip) = NULL;   /* set by the one-body dispatch */
static int suppress_index = -1;               /* an entry whose re-arrival is a hand-back rerun, not a new arrival */

static int hexval(char c) { return c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : c >= 'A' && c <= 'F' ? c - 'A' + 10 : -1; }
static bool unhex(const std::string &s, std::vector<uint8_t> &out) {
    if (s.size() % 2) return false;
    out.clear();
    for (size_t k = 0; k < s.size(); k += 2) {
        int hi = hexval(s[k]), lo = hexval(s[k + 1]);
        if (hi < 0 || lo < 0) return false;
        out.push_back((uint8_t)(hi * 16 + lo));
    }
    return true;
}

static void report(void) {
    if (state != 2) return;
    std::string path = log_base + ".tsv";
    FILE *f = fopen(path.c_str(), "w");
    if (!f) return;
    unsigned reached = 0;
    for (size_t k = 0; k < entries.size(); ++k) if (entries[k].count) ++reached;
    fprintf(f, "# stage0 observer: registry_unique=%u skipped_not_unique=%u reached=%u arrivals=%llu instructions=%llu seq_lines=%llu seq_cap=%llu\n",
            (unsigned)entries.size(), (unsigned)skipped.size(), reached, (unsigned long long)arrivals, (unsigned long long)insns,
            (unsigned long long)seq_lines, (unsigned long long)SEQ_CAP);
    for (size_t k = 0; k < skipped.size(); ++k) fprintf(f, "#skipped\t%s\n", skipped[k].c_str());
    fprintf(f, "# id\tarrivals\tfirst_instruction\tfirst_cs\n");
    for (size_t k = 0; k < entries.size(); ++k)
        fprintf(f, "%s\t%llu\t%llu\t%04X\n", entries[k].id.c_str(), (unsigned long long)entries[k].count,
                (unsigned long long)entries[k].first_insn, entries[k].first_cs);
    fclose(f);
    if (seq) fflush(seq);
}

static void load(void) {
    const char *reg = getenv("PR_HYBRID_REGISTRY");
    state = 1;
    if (!reg || !*reg) return;
    FILE *f = fopen(reg, "r");
    if (!f) { fprintf(stderr, "PR_HYBRID: cannot open registry %s\n", reg); return; }
    by_ip.assign(65536, std::vector<int>()); hit.assign(65536, 0);
    char line[4096];
    while (fgets(line, sizeof line, f)) {
        if (line[0] == '#') continue;
        std::vector<std::string> col; std::string cur;
        for (char *p = line; *p && *p != '\n'; ++p) { if (*p == '\t') { col.push_back(cur); cur.clear(); } else cur += *p; }
        col.push_back(cur);
        if (col.size() < 6) { if (!col.empty() && !col[0].empty()) skipped.push_back(col[0] + " (no signature)"); continue; }
        if (col[5] != "unique") { skipped.push_back(col[0] + " (" + col[5] + ")"); continue; }
        Entry e; e.id = col[0]; e.ip = (uint16_t)strtoul(col[1].c_str(), NULL, 16); e.count = 0; e.first_insn = 0; e.first_cs = 0;
        if (!unhex(col[3], e.sig) || !unhex(col[4], e.mask) || e.sig.size() != e.mask.size() || e.sig.empty()) {
            skipped.push_back(e.id + " (bad row)"); continue;
        }
        by_ip[e.ip].push_back((int)entries.size()); hit[e.ip] = 1; entries.push_back(e);
    }
    fclose(f);
    const char *lb = getenv("PR_HYBRID_LOG");
    log_base = lb && *lb ? lb : "pr_hybrid_observer";
    seq = fopen((log_base + ".seq").c_str(), "w");
    if (seq) fprintf(seq, "# n\tid\tcs:ip\tinstruction\n");
    { const char *pv = getenv("PR_HYBRID_SEED_PIN"); if (pv && *pv) { pin_value = (uint32_t)strtoul(pv, NULL, 16); pin_state = 1; } }
    draws = fopen((log_base + ".draws").c_str(), "w");
    if (draws) { fprintf(draws, "# n\tinstruction\twall_ms\tcs:ip\trandseed_before (DS:4428, read at the step's entry)\n"); fflush(draws); }
    state = 2;
    atexit(report);
    fprintf(stderr, "PR_HYBRID observer: %u entries, %u skipped\n", (unsigned)entries.size(), (unsigned)skipped.size());
    report();
}

} // namespace pr_obs
#endif
