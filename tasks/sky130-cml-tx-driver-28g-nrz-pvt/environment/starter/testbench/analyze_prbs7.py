#!/usr/bin/env python3
"""Analyze prbs7_tran.csv (from tb_prbs7_tt.spi, via gen_prbs7.py) against
prbs7_bits.csv: eye height, symbol-sign errors, rise/fall time, overshoot/
undershoot, Vocm deviation, output range, deterministic jitter (pp/rms),
duty-cycle distortion, average power. Second-period-only per instruction.md
(discard first period). Zero crossings found by linear interpolation
between raw (0.2ps-max-step) samples, not rounded print values.
"""
import sys

UI = 1.0 / 28e9
N_BITS = 127

# static-level reference (from tb_static_tt.spi, tt/27C): settled +/-Vod and
# the two-symbol Vocm mean. Passed as args so PVT reruns use their own values.


def load_tran(path):
    t, dinp, dinn, voutp, voutn, iddvdd = [], [], [], [], [], []
    for line in open(path):
        p = line.split()
        if len(p) >= 10:
            t.append(float(p[0]))
            dinp.append(float(p[1]))
            dinn.append(float(p[3]))
            voutp.append(float(p[5]))
            voutn.append(float(p[7]))
            iddvdd.append(float(p[9]))
    return t, dinp, dinn, voutp, voutn, iddvdd


def load_bits(path):
    idx, tid, bits = [], [], []
    for line in open(path):
        p = line.split()
        idx.append(int(p[0]))
        tid.append(float(p[1]))
        bits.append(int(p[2]))
    return idx, tid, bits


def interp_at(t, y, target):
    # binary search for bracketing indices
    lo, hi = 0, len(t) - 1
    if target <= t[0]:
        return y[0]
    if target >= t[-1]:
        return y[-1]
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if t[mid] <= target:
            lo = mid
        else:
            hi = mid
    frac = (target - t[lo]) / (t[hi] - t[lo])
    return y[lo] + frac * (y[hi] - y[lo])


def find_crossing(t, y, t_guess, window, level=0.0):
    """Find y(t)=level crossing nearest t_guess within +-window, by linear
    interpolation between the two raw samples that bracket the crossing."""
    lo_t, hi_t = t_guess - window, t_guess + window
    lo = 0
    while lo < len(t) and t[lo] < lo_t:
        lo += 1
    hi = lo
    while hi < len(t) and t[hi] <= hi_t:
        hi += 1
    candidates = []
    for i in range(max(lo, 1), min(hi, len(t))):
        y0, y1 = y[i - 1], y[i]
        if (y0 - level) == 0:
            candidates.append((t[i - 1], t[i - 1]))
            continue
        if (y0 - level) * (y1 - level) < 0:
            frac = (level - y0) / (y1 - y0)
            tc = t[i - 1] + frac * (t[i] - t[i - 1])
            candidates.append((abs(tc - t_guess), tc))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][1]


def main():
    if len(sys.argv) != 7:
        raise SystemExit(
            "usage: analyze_prbs7.py TRAN_CSV BITS_CSV VOD1_STATIC "
            "VOD0_STATIC VOCM_STATIC_MEAN VDD"
        )
    tran_csv, bits_csv = sys.argv[1], sys.argv[2]
    vod1_static = float(sys.argv[3])
    vod0_static = float(sys.argv[4])
    vocm_static_mean = float(sys.argv[5])
    vdd = float(sys.argv[6])

    t, dinp, dinn, voutp, voutn, iddvdd = load_tran(tran_csv)
    idx, tid, bits = load_bits(bits_csv)

    vod = [p - n for p, n in zip(voutp, voutn)]
    vocm = [(p + n) / 2 for p, n in zip(voutp, voutn)]

    swing = vod1_static - vod0_static
    lo_thr = vod0_static + 0.2 * swing
    hi_thr = vod0_static + 0.8 * swing

    second_period_start_idx = N_BITS  # bit index 127..253
    t0 = second_period_start_idx * UI

    # --- driver group delay (needed before any center-of-UI sampling) ---
    # "center-of-UI" has to mean the center of the *output's* UI, not the
    # nominal input bit-boundary grid: a real driver has nonzero propagation
    # delay from input transition to output crossing. instruction.md's
    # jitter definition already subtracts this same mean crossing-time
    # offset before computing jitter stats (a group-delay compensation);
    # the eye-height/sign/rise-fall sampling needs the identical
    # compensation for the same reason -- no real eye diagram or receiver
    # ever samples on the transmitter's raw, uncompensated bit clock.
    # The crossing search window is 0.9*UI (not 0.5*UI) so it stays wide
    # enough to find every transition once the timebase carries a
    # comparable delay offset; a too-narrow window would silently drop
    # crossings rather than erroring, understating both eye height and
    # jitter.
    delay_errs = []
    for n in range(second_period_start_idx + 1, 2 * N_BITS):
        if bits[n] == bits[n - 1]:
            continue
        tc = find_crossing(t, vod, n * UI, 0.9 * UI, 0.0)
        if tc is not None:
            delay_errs.append(tc - n * UI)
    group_delay = sum(delay_errs) / len(delay_errs)

    # --- eye height + sign check (center-of-UI sampling, delay-compensated) ---
    one_samples, zero_samples = [], []
    sign_errors = 0
    for n in range(second_period_start_idx, 2 * N_BITS):
        tc = (n + 0.5) * UI + group_delay
        v = interp_at(t, vod, tc)
        if bits[n] == 1:
            one_samples.append(v)
            if v <= 0:
                sign_errors += 1
        else:
            zero_samples.append(v)
            if v >= 0:
                sign_errors += 1
    eye_height = min(one_samples) - max(zero_samples)

    # --- rise/fall time, overshoot/undershoot on transitions in 2nd period ---
    rise_times, fall_times = [], []
    overshoot_max = 0.0
    undershoot_max = 0.0
    for n in range(second_period_start_idx + 1, 2 * N_BITS):
        if bits[n] == bits[n - 1]:
            continue
        t_nom = n * UI + group_delay
        rising = bits[n] == 1
        if rising:
            t_lo = find_crossing(t, vod, t_nom, 0.6 * UI, lo_thr)
            t_hi = find_crossing(t, vod, t_nom, 0.6 * UI, hi_thr)
            if t_lo is not None and t_hi is not None and t_hi > t_lo:
                rise_times.append(t_hi - t_lo)
        else:
            t_hi = find_crossing(t, vod, t_nom, 0.6 * UI, hi_thr)
            t_lo = find_crossing(t, vod, t_nom, 0.6 * UI, lo_thr)
            if t_lo is not None and t_hi is not None and t_lo > t_hi:
                fall_times.append(t_lo - t_hi)

    # overshoot/undershoot over the whole 2nd-period window
    for i in range(len(t)):
        if t[i] < t0:
            continue
        v = vod[i]
        if v > vod1_static:
            overshoot_max = max(overshoot_max, v - vod1_static)
        if v < vod0_static:
            undershoot_max = max(undershoot_max, vod0_static - v)

    # --- Vocm deviation ---
    vocm_dev_max = 0.0
    for i in range(len(t)):
        if t[i] < t0:
            continue
        vocm_dev_max = max(vocm_dev_max, abs(vocm[i] - vocm_static_mean))

    # --- output range ---
    vmin = min(min(voutp[i], voutn[i]) for i in range(len(t)) if t[i] >= t0)
    vmax = max(max(voutp[i], voutn[i]) for i in range(len(t)) if t[i] >= t0)

    # --- deterministic jitter ---
    crossing_errors = []
    rising_errors, falling_errors = [], []
    for n in range(second_period_start_idx + 1, 2 * N_BITS):
        if bits[n] == bits[n - 1]:
            continue
        t_nom = n * UI
        tc = find_crossing(t, vod, t_nom, 0.9 * UI, 0.0)
        if tc is None:
            continue
        err = tc - t_nom
        crossing_errors.append(err)
        if bits[n] == 1:
            rising_errors.append(err)
        else:
            falling_errors.append(err)

    mean_err = sum(crossing_errors) / len(crossing_errors)
    adj = [e - mean_err for e in crossing_errors]
    pp_jitter = max(adj) - min(adj)
    rms_jitter = (sum(e * e for e in adj) / len(adj)) ** 0.5
    mean_rise = sum(rising_errors) / len(rising_errors) if rising_errors else 0.0
    mean_fall = sum(falling_errors) / len(falling_errors) if falling_errors else 0.0
    dcd = abs(mean_rise - mean_fall)

    # --- power ---
    idd_vals = [iddvdd[i] for i in range(len(t)) if t[i] >= t0]
    avg_power = vdd * (sum(idd_vals) / len(idd_vals))

    print(f"n_transitions_in_2nd_period = {len(crossing_errors)}")
    print(f"eye_height_mV = {eye_height*1e3:.3f}")
    print(f"sign_errors = {sign_errors}")
    print(f"rise_time_ps: n={len(rise_times)} "
          f"max={max(rise_times)*1e12 if rise_times else float('nan'):.4f} "
          f"mean={sum(rise_times)/len(rise_times)*1e12 if rise_times else float('nan'):.4f}")
    print(f"fall_time_ps: n={len(fall_times)} "
          f"max={max(fall_times)*1e12 if fall_times else float('nan'):.4f} "
          f"mean={sum(fall_times)/len(fall_times)*1e12 if fall_times else float('nan'):.4f}")
    print(f"overshoot_mV = {overshoot_max*1e3:.3f}  "
          f"({overshoot_max/swing*100:.2f}% of swing)")
    print(f"undershoot_mV = {undershoot_max*1e3:.3f}  "
          f"({undershoot_max/swing*100:.2f}% of swing)")
    print(f"vocm_dev_max_mV = {vocm_dev_max*1e3:.3f}")
    print(f"output_range_V = [{vmin:.4f}, {vmax:.4f}]")
    print(f"jitter_pp_ps = {pp_jitter*1e12:.4f}")
    print(f"jitter_rms_ps = {rms_jitter*1e12:.4f}")
    print(f"dcd_ps = {dcd*1e12:.4f}")
    print(f"avg_power_mW = {avg_power*1e3:.4f}")


if __name__ == "__main__":
    main()
