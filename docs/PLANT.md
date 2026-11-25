# Plant: ONE SOLAR (Divjake)

The single source of truth for parameters is `config/plant.yaml`. Every value there has a status: CONFIRMED, PROVISIONAL or UNKNOWN.

## Known (owner statements, 2026-11-25)
- Company: ONE SOLAR shpk (owner confirmed). NIPT not provided yet.
- Location: Divjake, Fier county. The model uses the town centre (PROVISIONAL) until exact coordinates are known.
- Size: "15.5 MW", which the owner believes is DC (MWp). Treated as 15.5 MWp DC, PROVISIONAL.
- Sales: fully merchant on ALPEX. No support scheme, no PPA, no trader offers yet.
- Batteries: planned, size unknown.
- Start of production: about 5 to 10 months after 2026-11-25.

## Needed from the design / construction documents
1. Exact site coordinates (or the cadastral parcel).
2. DC MWp, inverter model and count, and total AC MW.
3. Grid connection agreement: export limit (MW) and metering point.
4. Mounting: fixed tilt (angle, azimuth, row spacing) or single-axis tracker (max angle, GCR).
5. Module model (temperature coefficient, bifacial or not).
6. Energy yield study (e.g. PVsyst P50/P90), used to check this model.
7. Battery power (MW) and energy (MWh), and whether it is DC- or AC-coupled.

Until then, every production figure is a **MODELED-PROVISIONAL scenario**, not expected generation.
