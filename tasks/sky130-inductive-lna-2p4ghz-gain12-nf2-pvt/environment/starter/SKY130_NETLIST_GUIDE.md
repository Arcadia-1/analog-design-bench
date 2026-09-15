# SKY130 netlist reference

This reference lists SKY130 SPICE device syntax, geometry conventions, hierarchy rules, simulation corners, and measurement definitions.

## Model selection

Load the required SKY130 model library in the testbench and select the intended process corner with `.lib`. Keep model loading out of the circuit under test so that the same circuit can be reused with different corners and model installations.

```spice
.lib "/path/to/sky130.lib.spice" tt
```

Use a model set that contains every device instantiated by the circuit. Core CMOS simulations may need only the continuous MOS models, while physical resistors, capacitors, varactors, inductors, BJTs, and specialized devices require their corresponding PDK models.

## MOS devices

The commonly used 1.8 V core and low-threshold MOS wrappers are:

```spice
sky130_fd_pr__nfet_01v8
sky130_fd_pr__pfet_01v8
sky130_fd_pr__nfet_01v8_lvt
sky130_fd_pr__pfet_01v8_lvt
```

The 5.0 V-gate/10.5 V-drain MOS wrappers are:

```spice
sky130_fd_pr__nfet_g5v0d10v5
sky130_fd_pr__pfet_g5v0d10v5
```

Instantiate MOS wrappers as four-terminal subcircuits:

```spice
XMN drain gate source bulk sky130_fd_pr__nfet_01v8 l=0.15 w=0.84 nf=2
XMP drain gate source bulk sky130_fd_pr__pfet_01v8 l=0.15 w=1.68 nf=2
XNHV drain gate source bulk sky130_fd_pr__nfet_g5v0d10v5 l=0.5 w=10 nf=5
XPHV drain gate source bulk sky130_fd_pr__pfet_g5v0d10v5 l=0.5 w=20 nf=5
```

The terminal order is drain, gate, source, bulk.

The SKY130 ngspice model libraries set `scale=1u`; therefore, numeric `l` and `w` values are expressed in micrometres and do not use a `u` suffix.

| Wrapper | Minimum modeled `l` (µm) |
| --- | ---: |
| `sky130_fd_pr__nfet_01v8` | `0.15` |
| `sky130_fd_pr__pfet_01v8` | `0.15` |
| `sky130_fd_pr__nfet_01v8_lvt` | `0.15` |
| `sky130_fd_pr__pfet_01v8_lvt` | `0.35` |
| `sky130_fd_pr__nfet_g5v0d10v5` | `0.50` |
| `sky130_fd_pr__pfet_g5v0d10v5` | `0.50` |

The `w` parameter is total channel width, `nf` is the positive integer number of fingers, and `w/nf` is the width of one finger.

## Subcircuits and hierarchy

Define a subcircuit with `.subckt` and terminate it with `.ends`:

```spice
.subckt example vss ibias vdd vinn vinp vout
* Circuit implementation.
.ends example
```

Nodes listed after the subcircuit name are external terminals. Other nodes are local to the subcircuit, except node `0` and nodes declared with `.global`.

## Passive and RF devices

Ideal passives use ordinary SPICE syntax:

```spice
R1 n1 n2 10k
C1 n2 vss 2p
L1 n3 n4 4n
```

SPICE suffixes are case-insensitive, and `M` means milli rather than mega. Use `meg` for mega.

Use a physical PDK passive when a task requires its process, temperature, voltage, geometry, or mismatch behaviour. Ideal `R` and `C` primitives have none of those layout-dependent PDK effects. A task may still allow ideal passives for an explicitly idealized load, compensation, or test structure; the task instruction and verifier, rather than this general reference, decide whether they are legal.

### Physical resistors

Physical poly-resistor wrappers have three terminals in `r0 r1 sub` order: connect `sub` to the appropriate substrate/reference node (normally `vss` for a low-voltage NMOS process). Set numeric `w` and `l` in micrometres; add a documented multiplier only when the selected wrapper supports it. Typical available choices are `sky130_fd_pr__res_high_po` and `sky130_fd_pr__res_xhigh_po`; use the model required or permitted by the task.

```spice
XRH r0 r1 vss sky130_fd_pr__res_high_po  w=1 l=10
XRX r0 r1 vss sky130_fd_pr__res_xhigh_po w=1 l=10
```

### Physical capacitors and varactors

The two-terminal MIM capacitor uses `c0 c1` order. Set its numeric `w`, `l`, and `mf` geometry parameters in micrometres/units expected by the PDK wrapper:

```spice
XCM c0 c1 sky130_fd_pr__cap_mim_m3_1 w=5 l=5 mf=1
```

Use the wrapper's documented `mf` parameter for physical MIM geometry. Do not
assume that generic SPICE instance `m`, a wrapper parameter named `mult`, and
`mf` are interchangeable: their electrical effect depends on the selected PDK
wrapper and simulator. A task that limits capacitor area must state which
forms it accepts and how it accounts for them. MIM density and corner scaling
are also model-dependent; use the task's stated area-accounting rule rather
than inferring a signoff capacitance from this example.

The low-threshold varactor is a three-terminal device in `c0 c1 b` order; `b` is its body/bias terminal. It accepts `w`, `l`, and `vm`:

```spice
XCV c0 c1 b sky130_fd_pr__cap_var_lvt w=5 l=0.5 vm=1
```

The commonly available SKY130 inductor wrappers are:

```spice
sky130_fd_pr__ind_03_90
sky130_fd_pr__ind_05_125
sky130_fd_pr__ind_05_220
```

These inductors use `a b ct sub` terminal order.

## Testbench organization

The testbench contains model selection, sources, circuit instances, loads, analyses, and measurements.

A directly runnable nominal testbench can use this pattern:

```spice
.lib "/path/to/sky130.lib.spice" tt
.include "circuit.spi"
.param supply=1.8
.param temperature=27
.temp {temperature}
VSS vss 0 0
VDD vdd vss {supply}
* Inputs, circuit instance, load, analysis, and measurements.
.end
```

## Process corners

The standard MOS process-corner sections are `tt`, `ff`, `ss`, `fs`, and `sf`. Supply voltage and temperature are specified independently by circuit sources and `.temp`.

## Monte Carlo simulation

The SKY130 model libraries provide separate sections for global process variation, local mismatch, and deterministic corners.

Common continuous-model modes are:

```spice
* Global process variation.
.option seed=31000
.lib "/path/to/sky130.lib.spice" mc

* Local mismatch around the typical corner.
.option seed=31000
.lib "/path/to/sky130.lib.spice" tt_mm

* Global variation with local mismatch enabled.
.option seed=31000
.lib "/path/to/sky130.lib.spice" mc
.param MC_MM_SWITCH=1
```

Place `.option seed` before `.lib`. The `mc` section enables global process variation, `tt_mm` enables local mismatch at the typical corner, and setting `MC_MM_SWITCH=1` with `mc` enables local mismatch in addition to global process variation.

## Measurements

Transient simulations should define initial state, pulse timing, source impedance, load, maximum step, and stop time. Sampled-data circuits should also define the sampling edge, resolving edge, and output-valid time.

Ordinary `.measure` statements can extract scalar results:

```spice
.measure tran trise TRIG v(vout) VAL=0.18 RISE=1 TARG v(vout) VAL=1.62 RISE=1
.measure tran tfall TRIG v(vout) VAL=1.62 FALL=1 TARG v(vout) VAL=0.18 FALL=1
```

Choose thresholds from the applicable signal range, make sure delay measurements pair edges from the same event, and use a time step fine enough to resolve the quantity being measured.

Measure settling against the commanded or independently known final value rather than the waveform's own tail average when static error is part of the requirement.

Measure kickback with a defined source impedance and sampling network. An ideal zero-ohm voltage source suppresses input disturbance and does not represent realistic kickback.

For AC, noise, and RF simulations, state the bias condition, source and load definitions, feedback condition, metric definition, and frequency or integration range. Voltage gain alone does not establish impedance matching or power transfer.

## Operating-point checks and convergence

MOS operating-point quantities include `gm`, `gds`, `vds`, `vdsat`, `id`, and terminal capacitances. The saturation-margin expression is `|VDS|-|VDSAT|`.

Floating nodes, ideal voltage-source loops, and ideal current-source cut sets can produce a singular operating-point matrix.

## Review checklist

- The top-level subcircuit name and pin order are correct.
- Every device uses the intended model and terminal order.
- Geometry values lie within the selected model's range.
- `w/nf` is the intended per-finger width.
- Physical passives use the documented terminal order and parameter names.
- The selected library section contains every instantiated device model.
