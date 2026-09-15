"""PRBS7 eye/jitter/power reduction, delay-compensated.

Eye-height sampling is referenced to the *output* signal's own mean
propagation (group) delay, not to the input bit clock: the driver has a
finite delay from input transition to output crossing, so raw
(n+0.5)*UI sampling in the input timebase would sample the output well
off its actual eye center. Group delay is computed first (mean crossing-
time offset over all transitions), then eye samples are taken at
(n+0.5)*UI + group_delay. The crossing search window is correspondingly
widened to 0.9*UI (instead of 0.5*UI) so it stays wide enough to find
every transition once the timebase carries a comparable offset."""

UI = 1.0 / 28e9
N_BITS = 127


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


def analyze(tran_csv, bits_csv, vod1_static, vod0_static, vocm_static_mean, vdd):
    t, dinp, dinn, voutp, voutn, iddvdd = load_tran(tran_csv)
    idx, tid, bits = load_bits(bits_csv)

    vod = [p - n for p, n in zip(voutp, voutn)]
    vocm = [(p + n) / 2 for p, n in zip(voutp, voutn)]

    swing = vod1_static - vod0_static
    lo_thr = vod0_static + 0.2 * swing
    hi_thr = vod0_static + 0.8 * swing

    second_period_start_idx = N_BITS
    t0 = second_period_start_idx * UI

    delay_errs = []
    for n in range(second_period_start_idx + 1, 2 * N_BITS):
        if bits[n] == bits[n - 1]:
            continue
        tc = find_crossing(t, vod, n * UI, 0.9 * UI, 0.0)
        if tc is not None:
            delay_errs.append(tc - n * UI)
    if not delay_errs:
        return {"n_transitions": 0}
    group_delay = sum(delay_errs) / len(delay_errs)

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

    for i in range(len(t)):
        if t[i] < t0:
            continue
        v = vod[i]
        if v > vod1_static:
            overshoot_max = max(overshoot_max, v - vod1_static)
        if v < vod0_static:
            undershoot_max = max(undershoot_max, vod0_static - v)

    vocm_dev_max = 0.0
    for i in range(len(t)):
        if t[i] < t0:
            continue
        vocm_dev_max = max(vocm_dev_max, abs(vocm[i] - vocm_static_mean))

    vmin = min(min(voutp[i], voutn[i]) for i in range(len(t)) if t[i] >= t0)
    vmax = max(max(voutp[i], voutn[i]) for i in range(len(t)) if t[i] >= t0)

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
        (rising_errors if bits[n] == 1 else falling_errors).append(err)

    mean_err = sum(crossing_errors) / len(crossing_errors)
    adj = [e - mean_err for e in crossing_errors]
    pp_jitter = max(adj) - min(adj)
    rms_jitter = (sum(e * e for e in adj) / len(adj)) ** 0.5
    mean_rise = sum(rising_errors) / len(rising_errors) if rising_errors else 0.0
    mean_fall = sum(falling_errors) / len(falling_errors) if falling_errors else 0.0
    dcd = abs(mean_rise - mean_fall)

    idd_vals = [iddvdd[i] for i in range(len(t)) if t[i] >= t0]
    avg_power = vdd * (sum(idd_vals) / len(idd_vals))

    return {
        "n_transitions": len(crossing_errors),
        "eye_height_v": eye_height,
        "sign_errors": sign_errors,
        "rise_time_s": max(rise_times) if rise_times else float("inf"),
        "fall_time_s": max(fall_times) if fall_times else float("inf"),
        "n_rise": len(rise_times),
        "n_fall": len(fall_times),
        "overshoot_v": overshoot_max,
        "undershoot_v": undershoot_max,
        "vocm_dev_max_v": vocm_dev_max,
        "vmin": vmin,
        "vmax": vmax,
        "jitter_pp_s": pp_jitter,
        "jitter_rms_s": rms_jitter,
        "dcd_s": dcd,
        "avg_power_w": avg_power,
    }
