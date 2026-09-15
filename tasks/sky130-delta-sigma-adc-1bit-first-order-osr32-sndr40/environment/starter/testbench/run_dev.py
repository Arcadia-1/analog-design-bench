#!/usr/bin/env python3
"""Run two public transistor-level records and print FFT/transfer diagnostics."""
import math
import subprocess
import tempfile
from pathlib import Path

import numpy as np

N = 512
FS = 10e6
TS = 1 / FS
DAC_DIFF = 0.8
HERE = Path(__file__).resolve().parent
CASES = (
    {"name": "pos", "offset": 0.01, "amp": 0.20, "phase": 0.0},
    {"name": "inv", "offset": -0.01, "amp": 0.20, "phase": 180.0},
)


def run_case(work, case):
    raw = Path(f"/tmp/ns_dev_{case['name']}_raw.txt")
    raw.unlink(missing_ok=True)
    source = (HERE / "tb_ns_dev.spi").read_text()
    for old, new in {
        ".param INPUT_OFFSET=0.01": f".param INPUT_OFFSET={case['offset']}",
        ".param INPUT_AMP=0.16": f".param INPUT_AMP={case['amp']}",
        ".param INPUT_PHASE=60": f".param INPUT_PHASE={case['phase']}",
        "/tmp/ns_dev_CASE_raw.txt": str(raw),
    }.items():
        source = source.replace(old, new, 1)
    deck = Path(work) / f"tb_ns_dev_{case['name']}.spi"
    deck.write_text(source)
    result = subprocess.run(["ngspice", "-b", deck], cwd=work, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode or not raw.exists():
        raise RuntimeError(result.stdout[-4000:])
    data = np.loadtxt(raw)
    t = data[:, 0]
    sample_t = t[0] + np.arange(int((t[-1] - t[0]) / TS) + 1) * TS + 20e-9
    idx = np.clip(np.searchsorted(t, sample_t, side="right") - 1, 0, len(t) - 1)
    ctrl_a = data[idx, 1]
    ctrl_b = data[idx, 3]
    finite = np.isfinite(ctrl_a) & np.isfinite(ctrl_b)
    ah = ctrl_a > 0.9
    bh = ctrl_b > 0.9
    complementary = (finite & (ah != bh))[-N:]
    code = (1.0 - 2.0 * ah.astype(float))[-N:]
    coeff = np.fft.fft(code - code.mean()) / N
    mag = np.abs(coeff)
    signal_bin = 3
    sndr = {}
    for osr in (16, 32):
        edge = N // (2 * osr)
        noise = sum(mag[k] ** 2 for k in range(1, edge + 1) if k != signal_bin)
        sndr[osr] = 10 * math.log10(mag[signal_bin] ** 2 / noise)
    ib = np.mean([mag[k] ** 2 for k in range(1, 9) if k != signal_bin])
    ob = np.mean(mag[9:256] ** 2)
    return {
        "coeff": coeff[signal_bin],
        "gain": DAC_DIFF * 2 * mag[signal_bin] / (2 * case["amp"]),
        "dc": float(code.mean()), "sndr": sndr,
        "dc_error": abs(float(code.mean()) - 2 * case["offset"] / DAC_DIFF),
        "density": float(np.mean(code > 0)),
        "transitions": float(np.mean(code[1:] != code[:-1])),
        "complementary": float(np.mean(complementary)),
        "invalid": int(np.count_nonzero(~complementary)),
        "shaping": 10 * math.log10(ob / ib),
        "state": float(np.max(np.abs(data[:, 5] - data[:, 7]))),
        "power": -1.8 * float(np.mean(data[:, 9])),
    }


def main():
    records = []
    with tempfile.TemporaryDirectory(prefix="ns-adc-public-") as work:
        for case in CASES:
            records.append(run_case(work, case))
    ratio = records[1]["coeff"] / records[0]["coeff"]
    phase_error = abs(math.degrees(math.atan2(math.sin(np.angle(ratio) - math.pi),
                                              math.cos(np.angle(ratio) - math.pi))))
    for case, record in zip(CASES, records):
        delta = record["sndr"][32] - record["sndr"][16]
        print(f"{case['name']} (unscored bin 3): gain={record['gain']:.3f} "
              f"dc={record['dc']:.4f} dc_error={record['dc_error']:.4f} "
              f"SNDR16={record['sndr'][16]:.2f}dB SNDR32={record['sndr'][32]:.2f}dB "
              f"SNDR32-SNDR16={delta:.2f}dB shaping={record['shaping']:.1f}dB "
              f"density={record['density']:.3f} transitions={100*record['transitions']:.1f}% "
              f"complementary={100*record['complementary']:.1f}% invalid={record['invalid']} "
              f"state={record['state']:.3f}V power={1e3*record['power']:.3f}mW")
    print(f"inversion magnitude ratio={abs(ratio):.3f}, phase error={phase_error:.2f}deg")


if __name__ == "__main__":
    main()
