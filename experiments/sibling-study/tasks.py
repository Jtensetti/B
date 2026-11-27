"""Frozen task specifications, public smoke tests, and hidden independent oracles for Study B.

Three distinct tasks, each with 6 sequential stages (Stage 0 from empty file + Stages 1..5):
  - T1_release_gate : Artifact release gatekeeper (B uses py + net + js)
  - T2_telemetry_sla: Telemetry & SLA stream auditor (B uses py + go + rs)
  - T3_freight_quote: Cross-border freight quote engine (B uses net + js + go)
"""
from __future__ import annotations

import math
import posixpath
import re
import statistics
import urllib.parse
from typing import Any


# ---------------------------------------------------------------------------
# Independent Reference Oracles (ground truth for all 6 languages)
# ---------------------------------------------------------------------------

def _round_even(x: float) -> int:
    return round(float(x))


def _parse_semver(s: str) -> tuple[int, int, int, str | None] | None:
    m = re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-([0-9A-Za-z.-]+))?", s)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)


def _satisfies_caret(ver: str, rng: str) -> bool:
    pv = _parse_semver(ver)
    if pv is None or pv[3] is not None:
        return False
    m = re.fullmatch(r"\^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", rng)
    if not m:
        raise ValueError(f"Unsupported range {rng}")
    rx, ry, rz = int(m.group(1)), int(m.group(2)), int(m.group(3))
    vx, vy, vz, _ = pv
    if (vx, vy, vz) < (rx, ry, rz):
        return False
    if rx > 0:
        return vx == rx
    if ry > 0:
        return vx == 0 and vy == ry
    return vx == 0 and vy == 0 and vz == rz


def oracle_t1(stage: int, data: dict[str, Any]) -> dict[str, Any]:
    min_range: str = data["min_range"]
    artifacts: list[dict[str, Any]] = data["artifacts"]
    valid_channels = {"stable", "beta", "lts"}
    path_rx = re.compile(r"^[a-z0-9-]+/[0-9]+\.[0-9]+\.[0-9]+(-[a-z0-9.]+)?$")

    elig_flags: list[bool] = []
    exempt_flags: list[bool] = []
    oversize_count = 0
    total_kb = 0
    max_kb = 0
    eligible_kb = 0
    eligible_versions: list[str] = []

    for art in artifacts:
        size_kb = int(art["size_kb"])
        total_kb += size_kb
        if size_kb > max_kb:
            max_kb = size_kb
        is_oversize = size_kb > 5000
        if is_oversize:
            oversize_count += 1

        decoded = urllib.parse.unquote(art["raw_path"])
        norm = posixpath.normpath(decoded)
        ver = posixpath.basename(norm)
        pkg = posixpath.dirname(norm)
        chan = art["channel"]

        fmt_ok = bool(path_rx.fullmatch(norm)) and chan in valid_channels
        pv = _parse_semver(ver)
        base_ok = fmt_ok and _satisfies_caret(ver, min_range)
        if stage >= 1 and is_oversize:
            base_ok = False

        exempt_hit = False
        if stage >= 3:
            is_lts_sec = (
                fmt_ok
                and chan == "lts"
                and "security" in pkg
                and pv is not None
                and pv[3] is None
                and not is_oversize
            )
            if is_lts_sec and not base_ok:
                exempt_hit = True
            elig = base_ok or is_lts_sec
        else:
            elig = base_ok

        elig_flags.append(elig)
        exempt_flags.append(exempt_hit)
        if elig:
            eligible_kb += size_kb
            eligible_versions.append(ver)

    out: dict[str, Any] = {
        "total": len(artifacts),
        "eligible": sum(elig_flags),
        "total_kb": total_kb,
        "max_kb": max_kb,
    }
    if stage >= 1:
        out["oversize"] = oversize_count
    if stage >= 2:
        consec = sum(1 for a, b in zip(elig_flags, elig_flags[1:]) if (not a) and (not b))
        out["consecutive_rejects"] = consec
        out["freeze"] = consec >= 2
    if stage >= 3:
        out["exempt"] = sum(exempt_flags)
    if stage >= 4:
        budget_mb = float(data["budget_mb"])
        out["eligible_kb"] = eligible_kb
        out["within_budget"] = float(eligible_kb) <= budget_mb * 1024.0
    if stage >= 5:
        if eligible_versions:
            best = max(eligible_versions, key=lambda v: _parse_semver(v)[:3])  # type: ignore[index]
        else:
            best = None
        out["recommended"] = best
    return out


def oracle_t2(stage: int, data: dict[str, Any]) -> dict[str, Any]:
    sla_ms = float(data["sla_s"]) * 1000.0
    sla_ms_int = _round_even(sla_ms)
    samples: list[dict[str, Any]] = data["samples"]

    breach_flags: list[bool] = []
    ms_list: list[int] = []
    valid_ms: list[int] = []
    overage_ms = 0
    max_ms = 0
    bucket_zero = 0
    critical = 0
    warn_or_worse = 0
    invalid_labels = 0
    exempt_count = 0

    for s in samples:
        svc = s["service"].strip().lower()
        ms = int(s["ms"])
        offset = int(s["offset"])
        ms_list.append(ms)
        if ms > max_ms:
            max_ms = ms
        bucket = offset % 4  # Python % with positive divisor 4 == Euclidean remainder
        if bucket == 0:
            bucket_zero += 1

        label_ok = 2 <= len(svc) <= 12
        if not label_ok:
            invalid_labels += 1
        else:
            valid_ms.append(ms)

        if ms >= 200:
            warn_or_worse += 1
        if ms > 1000:
            critical += 1

        raw_breach = float(ms) > sla_ms
        is_exempt = stage >= 4 and svc == "healthcheck" and bucket == 0
        if raw_breach and is_exempt:
            exempt_count += 1
            breach = False
        else:
            breach = raw_breach
        breach_flags.append(breach)
        if breach:
            overage_ms += ms - sla_ms_int

    mean_src = valid_ms if stage >= 3 else ms_list
    mean_ms = _round_even(statistics.mean(mean_src)) if mean_src else 0

    out: dict[str, Any] = {
        "count": len(samples),
        "breaches": sum(breach_flags),
        "overage_ms": overage_ms,
        "max_ms": max_ms,
        "mean_ms": mean_ms,
        "bucket_zero": bucket_zero,
    }
    if stage >= 1:
        out["critical"] = critical
        out["warn_or_worse"] = warn_or_worse
    if stage >= 2:
        consec = sum(1 for a, b in zip(breach_flags, breach_flags[1:]) if a and b)
        spikes = sum(1 for a, b in zip(ms_list, ms_list[1:]) if b > a + 100)
        out["consecutive_breaches"] = consec
        out["spike_steps"] = spikes
    if stage >= 3:
        out["invalid_labels"] = invalid_labels
    if stage >= 4:
        out["exempt"] = exempt_count
    if stage >= 5:
        regressed = 0
        min_so_far: int | None = None
        for m in ms_list:
            if min_so_far is not None and min_so_far + 300 < m:
                regressed += 1
            if min_so_far is None or m < min_so_far:
                min_so_far = m
        consec = out["consecutive_breaches"]
        if consec >= 2 or critical > 0:
            status = "red"
        elif out["breaches"] > 0 or invalid_labels > 0:
            status = "yellow"
        else:
            status = "green"
        out["regressed"] = regressed
        out["status"] = status
    return out


def oracle_t3(stage: int, data: dict[str, Any]) -> dict[str, Any]:
    eur_to_sek = float(data["eur_to_sek"])
    legs: list[dict[str, Any]] = data["legs"]
    depot_rx = re.compile(r"^[a-z]{3}-[0-9]{2}$")
    valid_zones = {"SE", "EU", "NON-EU"}

    valid_kms: list[float] = []
    valid_eur_list: list[float] = []
    heavy_legs = 0
    customs_legs = 0
    vip_exempt = 0

    for leg in legs:
        norm = posixpath.normpath(leg["route"])
        depot = posixpath.basename(norm)
        zone = leg["zone"].strip().upper()
        if not depot_rx.fullmatch(depot) or zone not in valid_zones:
            continue
        dx = float(leg["dx_km"])
        dy = float(leg["dy_km"])
        km = math.sqrt(dx * dx + dy * dy)
        kg = float(leg["weight_g"]) / 1000.0
        base = 5.0 + 0.5 * km + 2.0 * kg

        fee = base
        is_heavy = kg >= 10.0
        if is_heavy:
            heavy_legs += 1
        if zone == "NON-EU":
            customs_legs += 1

        if stage >= 1:
            mult = 1.0 if km <= 50.0 else (1.15 if km <= 200.0 else 1.35)
            fee = base * mult
            is_vip = stage >= 4 and depot == "sto-01" and zone == "SE"
            if is_heavy:
                if is_vip:
                    vip_exempt += 1
                else:
                    fee += 12.0
        if stage >= 2:
            if zone == "SE":
                fee *= 0.9
            elif zone == "NON-EU":
                fee += 15.0

        valid_kms.append(km)
        valid_eur_list.append(fee)

    long_haul_pairs = sum(1 for a, b in zip(valid_kms, valid_kms[1:]) if a > 100.0 and b > 100.0)
    total_km = sum(valid_kms)
    total_eur = sum(valid_eur_list) + (25.0 * long_haul_pairs if stage >= 3 else 0.0)
    total_m = _round_even(total_km * 1000.0)
    total_eur_cents = _round_even(total_eur * 100.0)
    total_sek = _round_even(total_eur * eur_to_sek)

    out: dict[str, Any] = {
        "legs": len(legs),
        "valid_legs": len(valid_kms),
        "total_m": total_m,
        "total_eur_cents": total_eur_cents,
        "total_sek": total_sek,
    }
    if stage >= 1:
        out["heavy_legs"] = heavy_legs
    if stage >= 2:
        out["customs_legs"] = customs_legs
    if stage >= 3:
        out["long_haul_pairs"] = long_haul_pairs
    if stage >= 4:
        out["vip_exempt"] = vip_exempt
    if stage >= 5:
        out["within_cap"] = total_sek <= int(data["max_sek"])
        out["max_leg_eur_cents"] = max((_round_even(f * 100.0) for f in valid_eur_list), default=0)
    return out


# ---------------------------------------------------------------------------
# Test Inputs (Public smoke tests + Hidden Independent Oracle Suites)
# ---------------------------------------------------------------------------

def _t1_public(stage: int) -> list[dict[str, Any]]:
    base = [
        {
            "min_range": "^1.2.0",
            "budget_mb": 2.0,
            "artifacts": [
                {"raw_path": "core/1%2E4%2E0", "channel": "stable", "size_kb": 400},
                {"raw_path": "ui/v1/../1%2E1%2E0", "channel": "stable", "size_kb": 200},
                {"raw_path": "security-auth/0%2E9%2E5", "channel": "lts", "size_kb": 1500},
                {"raw_path": "media/1%2E5%2E0", "channel": "beta", "size_kb": 6000},
            ],
        },
        {
            "min_range": "^2.0.0",
            "budget_mb": 0.5,
            "artifacts": [
                {"raw_path": "api/1%2E9%2E0", "channel": "stable", "size_kb": 100},
                {"raw_path": "api/2%2E1%2E0-rc.1", "channel": "beta", "size_kb": 120},
                {"raw_path": "BAD/2%2E1%2E0", "channel": "stable", "size_kb": 80},
                {"raw_path": "api/2%2E10%2E0", "channel": "stable", "size_kb": 600},
                {"raw_path": "api/2%2E9%2E0", "channel": "stable", "size_kb": 50},
            ],
        },
    ]
    if stage < 4:
        return [{k: v for k, v in x.items() if k != "budget_mb"} for x in base]
    return base


def _t1_hidden(stage: int) -> list[dict[str, Any]]:
    cases = [
        {"min_range": "^1.0.0", "budget_mb": 1.0, "artifacts": []},
        {"min_range": "^1.2.0", "budget_mb": 5.0, "artifacts": [
            {"raw_path": "svc/1%2E2%2E0", "channel": "stable", "size_kb": 99},
            {"raw_path": "svc/1%2E2%2E1", "channel": "beta", "size_kb": 100},
            {"raw_path": "svc/1%2E10%2E0", "channel": "lts", "size_kb": 5000},
            {"raw_path": "svc/1%2E9%2E9", "channel": "stable", "size_kb": 5001},
        ]},
        {"min_range": "^0.2.0", "budget_mb": 2.0, "artifacts": [
            {"raw_path": "lib/0%2E2%2E0", "channel": "stable", "size_kb": 300},
            {"raw_path": "lib/0%2E2%2E9", "channel": "stable", "size_kb": 300},
            {"raw_path": "lib/0%2E3%2E0", "channel": "stable", "size_kb": 300},
            {"raw_path": "lib/0%2E2%2E10", "channel": "beta", "size_kb": 300},
        ]},
        {"min_range": "^3.0.0", "budget_mb": 1.5, "artifacts": [
            {"raw_path": "security-patch/1%2E0%2E0", "channel": "lts", "size_kb": 1024},
            {"raw_path": "security-patch/1%2E0%2E1-rc.1", "channel": "lts", "size_kb": 500},
            {"raw_path": "security-patch/2%2E0%2E0", "channel": "stable", "size_kb": 500},
            {"raw_path": "security-patch/1%2E0%2E2", "channel": "lts", "size_kb": 5001},
            {"raw_path": "security-core/3%2E1%2E0", "channel": "lts", "size_kb": 512},
        ]},
        {"min_range": "^1.0.0", "budget_mb": 1.0, "artifacts": [
            {"raw_path": "a/0%2E1%2E0", "channel": "stable", "size_kb": 10},
            {"raw_path": "b/0%2E2%2E0", "channel": "stable", "size_kb": 20},
            {"raw_path": "c/0%2E3%2E0", "channel": "stable", "size_kb": 30},
            {"raw_path": "d/0%2E4%2E0", "channel": "unknown", "size_kb": 40},
        ]},
        {"min_range": "^1.5.0", "budget_mb": 0.5, "artifacts": [
            {"raw_path": "x/y/../1%2E5%2E0", "channel": "stable", "size_kb": 512},
            {"raw_path": "x/y/1%2E6%2E0", "channel": "stable", "size_kb": 100},
            {"raw_path": "x/not-semver", "channel": "stable", "size_kb": 50},
            {"raw_path": "x/1%2E6%2E0", "channel": "preview", "size_kb": 50},
        ]},
        {"min_range": "^0.0.3", "budget_mb": 1.0, "artifacts": [
            {"raw_path": "micro/0%2E0%2E3", "channel": "stable", "size_kb": 100},
            {"raw_path": "micro/0%2E0%2E4", "channel": "stable", "size_kb": 100},
            {"raw_path": "security-micro/0%2E0%2E1", "channel": "lts", "size_kb": 200},
        ]},
        {"min_range": "^2.1.0", "budget_mb": 2.0, "artifacts": [
            {"raw_path": "core//2%2E1%2E0", "channel": "stable", "size_kb": 1024},
            {"raw_path": "core/2%2E2%2E0", "channel": "beta", "size_kb": 1024},
            {"raw_path": "core/2%2E2%2E1", "channel": "stable", "size_kb": 1},
        ]},
        {"min_range": "^1.0.0", "budget_mb": 10.0, "artifacts": [
            {"raw_path": "bad/0%2E1%2E0", "channel": "stable", "size_kb": 50},
            {"raw_path": "ok/1%2E0%2E0", "channel": "stable", "size_kb": 50},
            {"raw_path": "bad/0%2E2%2E0", "channel": "stable", "size_kb": 50},
            {"raw_path": "ok/1%2E1%2E0", "channel": "stable", "size_kb": 50},
            {"raw_path": "bad/0%2E3%2E0", "channel": "stable", "size_kb": 50},
        ]},
        {"min_range": "^4.0.0", "budget_mb": 3.0, "artifacts": [
            {"raw_path": "app-security/1%2E9%2E0", "channel": "lts", "size_kb": 1000},
            {"raw_path": "app-security/1%2E11%2E0", "channel": "lts", "size_kb": 1000},
            {"raw_path": "app-security/4%2E0%2E0", "channel": "lts", "size_kb": 1000},
        ]},
    ]
    if stage < 4:
        return [{k: v for k, v in x.items() if k != "budget_mb"} for x in cases]
    return cases


def _t2_public(stage: int) -> list[dict[str, Any]]:
    return [
        {
            "sla_s": 0.5,
            "samples": [
                {"service": " Auth ", "ms": 420, "offset": -5},
                {"service": "HealthCheck", "ms": 650, "offset": -4},
                {"service": "billing", "ms": 750, "offset": 3},
                {"service": "billing", "ms": 1100, "offset": 0},
            ],
        },
        {
            "sla_s": 0.25,
            "samples": [
                {"service": "🔥", "ms": 100, "offset": 1},
                {"service": "ok🔥", "ms": 200, "offset": 8},
                {"service": "api", "ms": 300, "offset": -8},
                {"service": "api", "ms": 620, "offset": 2},
            ],
        },
    ]


def _t2_hidden(stage: int) -> list[dict[str, Any]]:
    return [
        {"sla_s": 0.5, "samples": []},
        {"sla_s": 0.5, "samples": [
            {"service": "a", "ms": 100, "offset": 0},
            {"service": "too-long-service-name", "ms": 200, "offset": 4},
        ]},
        {"sla_s": 0.3, "samples": [
            {"service": "  Core  ", "ms": 150, "offset": -1},
            {"service": "core", "ms": 300, "offset": -4},
            {"service": "core", "ms": 301, "offset": -8},
            {"service": "core", "ms": 450, "offset": -3},
            {"service": "core", "ms": 460, "offset": 12},
        ]},
        {"sla_s": 0.4, "samples": [
            {"service": "healthcheck", "ms": 500, "offset": 0},
            {"service": "healthcheck", "ms": 520, "offset": -4},
            {"service": "healthcheck", "ms": 530, "offset": 1},
            {"service": "worker", "ms": 540, "offset": 2},
        ]},
        {"sla_s": 1.0, "samples": [
            {"service": "s1", "ms": 2, "offset": 0},
            {"service": "s2", "ms": 3, "offset": 1},
        ]},
        {"sla_s": 1.0, "samples": [
            {"service": "s1", "ms": 3, "offset": 0},
            {"service": "s2", "ms": 4, "offset": 1},
        ]},
        {"sla_s": 0.2, "samples": [
            {"service": "🚀", "ms": 500, "offset": 0},
            {"service": "🚀a", "ms": 100, "offset": 4},
            {"service": "éééééééééééé", "ms": 150, "offset": -4},
            {"service": "ééééééééééééé", "ms": 900, "offset": 1},
        ]},
        {"sla_s": 0.5, "samples": [
            {"service": "db", "ms": 500, "offset": 0},
            {"service": "db", "ms": 199, "offset": 1},
            {"service": "db", "ms": 200, "offset": 2},
            {"service": "db", "ms": 1000, "offset": 3},
            {"service": "db", "ms": 1001, "offset": 4},
        ]},
        {"sla_s": 0.6, "samples": [
            {"service": "web", "ms": 700, "offset": 1},
            {"service": "web", "ms": 350, "offset": 2},
            {"service": "web", "ms": 650, "offset": 3},
            {"service": "web", "ms": 651, "offset": 4},
        ]},
        {"sla_s": 0.5, "samples": [
            {"service": "healthcheck", "ms": 1200, "offset": 8},
            {"service": "api", "ms": 100, "offset": 1},
        ]},
    ]


def _t3_public(stage: int) -> list[dict[str, Any]]:
    base = [
        {
            "eur_to_sek": 11.5,
            "max_sek": 2500,
            "legs": [
                {"route": "hub//se/sto-01", "dx_km": 30.0, "dy_km": 40.0, "weight_g": 12000.0, "zone": " se "},
                {"route": "eu/de/../ber-02", "dx_km": 60.0, "dy_km": 80.0, "weight_g": 5000.0, "zone": "eu"},
                {"route": "us/nyc-99", "dx_km": 120.0, "dy_km": 160.0, "weight_g": 10000.0, "zone": "NON-EU"},
            ],
        },
        {
            "eur_to_sek": 11.2,
            "max_sek": 4000,
            "legs": [
                {"route": "eu/bad_depot", "dx_km": 10.0, "dy_km": 10.0, "weight_g": 1000.0, "zone": "EU"},
                {"route": "eu/par-03", "dx_km": 90.0, "dy_km": 120.0, "weight_g": 8000.0, "zone": "EU"},
                {"route": "eu/mad-04", "dx_km": 150.0, "dy_km": 200.0, "weight_g": 15000.0, "zone": "EU"},
            ],
        },
    ]
    if stage < 5:
        return [{k: v for k, v in x.items() if k != "max_sek"} for x in base]
    return base


def _t3_hidden(stage: int) -> list[dict[str, Any]]:
    cases = [
        {"eur_to_sek": 11.0, "max_sek": 0, "legs": []},
        {"eur_to_sek": 11.0, "max_sek": 500, "legs": [
            {"route": "a/BAD-01", "dx_km": 3.0, "dy_km": 4.0, "weight_g": 1000.0, "zone": "EU"},
            {"route": "a/sto-01", "dx_km": 3.0, "dy_km": 4.0, "weight_g": 1000.0, "zone": "MARS"},
        ]},
        {"eur_to_sek": 11.5, "max_sek": 1000, "legs": [
            {"route": "se/sto-01", "dx_km": 30.0, "dy_km": 40.0, "weight_g": 10000.0, "zone": "SE"},
            {"route": "se/got-02", "dx_km": 30.0, "dy_km": 40.0, "weight_g": 10000.0, "zone": "SE"},
        ]},
        {"eur_to_sek": 10.0, "max_sek": 5000, "legs": [
            {"route": "eu/lon-01", "dx_km": 60.0, "dy_km": 80.0, "weight_g": 2000.0, "zone": "NON-EU"},
            {"route": "eu/par-02", "dx_km": 80.0, "dy_km": 80.0, "weight_g": 3000.0, "zone": "EU"},
            {"route": "eu/invalid", "dx_km": 10.0, "dy_km": 10.0, "weight_g": 1000.0, "zone": "EU"},
            {"route": "eu/rom-03", "dx_km": 90.0, "dy_km": 120.0, "weight_g": 4000.0, "zone": "EU"},
        ]},
        {"eur_to_sek": 11.25, "max_sek": 10000, "legs": [
            {"route": "a/b/../sto-01", "dx_km": 0.0, "dy_km": 201.0, "weight_g": 20000.0, "zone": "se"},
            {"route": "a/sto-01", "dx_km": 0.0, "dy_km": 200.0, "weight_g": 20000.0, "zone": "EU"},
            {"route": "a/osl-05", "dx_km": 0.0, "dy_km": 150.0, "weight_g": 9999.0, "zone": "non-eu"},
        ]},
        {"eur_to_sek": 11.5, "max_sek": 200, "legs": [
            {"route": "se/mal-09", "dx_km": 0.0, "dy_km": 50.0, "weight_g": 500.0, "zone": "SE"},
        ]},
        {"eur_to_sek": 12.0, "max_sek": 3000, "legs": [
            {"route": "x/cph-01", "dx_km": 0.0, "dy_km": 100.0, "weight_g": 1000.0, "zone": "EU"},
            {"route": "x/cph-02", "dx_km": 0.0, "dy_km": 100.5, "weight_g": 1000.0, "zone": "EU"},
            {"route": "x/cph-03", "dx_km": 0.0, "dy_km": 101.0, "weight_g": 1000.0, "zone": "EU"},
            {"route": "x/cph-04", "dx_km": 0.0, "dy_km": 102.0, "weight_g": 1000.0, "zone": "EU"},
        ]},
        {"eur_to_sek": 11.4, "max_sek": 1500, "legs": [
            {"route": "nordic/hel-11", "dx_km": 9.0, "dy_km": 12.0, "weight_g": 10000.0, "zone": "EU"},
            {"route": "nordic/sto-01", "dx_km": 9.0, "dy_km": 12.0, "weight_g": 9999.0, "zone": "SE"},
            {"route": "nordic/sto-01", "dx_km": 9.0, "dy_km": 12.0, "weight_g": 10000.0, "zone": "SE"},
        ]},
        {"eur_to_sek": 10.5, "max_sek": 800, "legs": [
            {"route": "dir//sub/../zur-77", "dx_km": 5.0, "dy_km": 12.0, "weight_g": 2500.0, "zone": " NON-EU "},
        ]},
        {"eur_to_sek": 11.0, "max_sek": 6000, "legs": [
            {"route": "e/ams-10", "dx_km": 120.0, "dy_km": 160.0, "weight_g": 11000.0, "zone": "EU"},
            {"route": "e/bru-12", "dx_km": 30.0, "dy_km": 40.0, "weight_g": 1000.0, "zone": "EU"},
            {"route": "e/lux-13", "dx_km": 120.0, "dy_km": 160.0, "weight_g": 11000.0, "zone": "EU"},
        ]},
    ]
    if stage < 5:
        return [{k: v for k, v in x.items() if k != "max_sek"} for x in cases]
    return cases


# ---------------------------------------------------------------------------
# Stage Prompt Specifications (language-neutral + B ecosystem requirements)
# ---------------------------------------------------------------------------

TASKS: dict[str, dict[str, Any]] = {
    "T1_release_gate": {
        "title": "Artifact Release Gatekeeper",
        "b_required_ecosystems": ("py", "net", "js"),
        "b_ecosystem_note": (
            "In B, compose libraries from all 3 ecosystems: "
            "Python (`use py:urllib.parse as urls` + `foreign urls.unquote(Text) -> Text`), "
            ".NET (`use net:System.Text.RegularExpressions.Regex as Rx`), and "
            "Node/npm (`use js:\"node:path/posix\" as path` and `use js:semver as sv`). "
            "Express all business logic, units, records, decision tables, summaries, and history counts natively in B."
        ),
        "oracle": oracle_t1,
        "public": _t1_public,
        "hidden": _t1_hidden,
        "stages": [
            # Stage 0
            """## Stage 0 — Build From Empty File: Artifact Release Gatekeeper

Read a JSON object from stdin and print one JSON object to stdout.

### Input JSON Schema
```json
{"min_range": "^1.2.0", "artifacts": [{"raw_path": "core/1%2E4%2E0", "channel": "stable", "size_kb": 400}]}
```

### Rules
1. URL-decode `raw_path`, then normalize it as a POSIX path (`norm`).
2. Extract `ver = basename(norm)` and `pkg = dirname(norm)`.
3. An artifact has a valid format iff:
   - `norm` matches regex `^[a-z0-9-]+/[0-9]+\\.[0-9]+\\.[0-9]+(-[a-z0-9.]+)?$`
   - `channel` is one of `"stable"`, `"beta"`, `"lts"`.
4. An artifact is `eligible` iff it has a valid format AND `ver` is a valid semver satisfying `min_range` (standard npm caret range `^X.Y.Z`, rejecting prereleases).
5. Compute over all input artifacts:
   - `total`: total number of artifacts
   - `eligible`: number of eligible artifacts
   - `total_kb`: sum of `size_kb` over all artifacts
   - `max_kb`: maximum `size_kb` over all artifacts (`0` if empty).

### Output JSON Schema
`{"total": int, "eligible": int, "total_kb": int, "max_kb": int}`""",

            # Stage 1
            """## Stage 1 — Change 1: Size Tier Classification

Preserve all Stage 0 behavior and add size tier rules:
1. Classify each artifact's `size_kb` into a tier:
   - `< 100` -> `"tiny"`
   - `<= 1000` -> `"standard"`
   - `<= 5000` -> `"large"`
   - `else` -> `"oversize"`
2. `"oversize"` artifacts (`size_kb > 5000`) are **NOT eligible** even if their path and semver are valid.
3. Add `"oversize"` (count of all input artifacts with `size_kb > 5000`) to the output JSON.

### Output JSON Schema
`{"total": int, "eligible": int, "oversize": int, "total_kb": int, "max_kb": int}`""",

            # Stage 2
            """## Stage 2 — Change 2: Consecutive Rejection Freeze

Preserve all Stage 0–1 behavior and add:
1. `consecutive_rejects`: count of adjacent pairs `(prev, curr)` in the input `artifacts` order where BOTH `prev` and `curr` are NOT eligible.
2. `freeze`: `true` if `consecutive_rejects >= 2`, else `false`.

### Output JSON Schema
`{"total": int, "eligible": int, "oversize": int, "total_kb": int, "max_kb": int, "consecutive_rejects": int, "freeze": bool}`""",

            # Stage 3
            """## Stage 3 — Change 3: LTS Security Exemption

Preserve all Stage 0–2 behavior and add an exemption rule:
1. An artifact is **LTS-security exempt** if:
   - It has a valid format (`norm` matches the regex and `channel == "lts"`)
   - `pkg` (`dirname(norm)`) contains `"security"`
   - `ver` is a valid **non-prerelease** semver (contains no `"-"`)
   - `size_kb <= 5000` (not oversize)
2. An exempt artifact is **eligible** even if its version does not satisfy `min_range`.
3. `exempt`: count of artifacts that became eligible ONLY because of this exemption (i.e., exempt rule matched AND it did NOT already satisfy `min_range`).
4. `total_kb` and `max_kb` MUST remain unchanged (still over all input artifacts). `consecutive_rejects` and `freeze` reflect the updated eligibility.

### Output JSON Schema
Add `"exempt": int` to Stage 2's output JSON.""",

            # Stage 4
            """## Stage 4 — Change 4: Storage Budget in MB vs KB

Preserve all Stage 0–3 behavior and update the input/output:
1. Input JSON now includes `"budget_mb": float` (storage budget in megabytes, where `1 MB = 1024 KB`).
   - In B, model `kb` and `mb` with `unit kb` and `unit mb = 1024 kb`.
2. Compute:
   - `eligible_kb`: sum of `size_kb` over **eligible** artifacts only (`0` if none).
   - `within_budget`: `true` if `eligible_kb <= budget_mb * 1024.0`, else `false`.

### Output JSON Schema
Add `"eligible_kb": int, "within_budget": bool` to Stage 3's output JSON.""",

            # Stage 5
            """## Stage 5 — Change 5: Recommended Highest Eligible Version

Preserve all Stage 0–4 behavior and add:
1. `recommended`: the highest semantic version string (`major.minor.patch`) among all **eligible** artifacts (including exempt ones; e.g., `"2.10.0"` > `"2.9.0"`), or `null` if no artifact is eligible.
   - Note: in B/TS, `semver.maxSatisfying(eligible_versions, ">=0.0.0")` selects the highest non-prerelease semver version!

### Output JSON Schema
Add `"recommended": string | null` to Stage 4's output JSON.""",
        ],
    },

    "T2_telemetry_sla": {
        "title": "Telemetry & SLA Stream Auditor",
        "b_required_ecosystems": ("py", "go", "rs"),
        "b_ecosystem_note": (
            "In B, compose libraries from all 3 ecosystems: "
            "Python (`use py:statistics as stats`), "
            "Go (`use go:strings as gstr`, `use go:math as gmath`), and "
            "Rust (`use rs:std.str as rstr`, `use rs:std.i64 as ri`). "
            "Use B units (`unit ms`, `unit s = 1000 ms`), records, decision tables, summaries, and ordered history counts."
        ),
        "oracle": oracle_t2,
        "public": _t2_public,
        "hidden": _t2_hidden,
        "stages": [
            # Stage 0
            """## Stage 0 — Build From Empty File: Telemetry & SLA Stream Auditor

Read a JSON object from stdin and print one JSON object to stdout.

### Input JSON Schema
```json
{"sla_s": 0.5, "samples": [{"service": " Auth ", "ms": 420, "offset": -5}]}
```

### Rules
1. Convert `sla_s` (seconds) to milliseconds `sla_ms = sla_s * 1000.0` (in B, use `unit ms` and `unit s = 1000 ms`). Let `sla_ms_int` be banker's half-to-even rounded integer of `sla_ms`.
2. Normalize each `service` name by trimming surrounding whitespace and converting to lowercase.
3. A sample breaches SLA iff `float(ms) > sla_ms`.
4. Compute:
   - `count`: total number of samples
   - `breaches`: number of breaching samples
   - `overage_ms`: sum of `(ms - sla_ms_int)` over breaching samples (`0` if none)
   - `max_ms`: maximum `ms` over all samples (`0` if empty)
   - `mean_ms`: banker's half-to-even rounded integer of the arithmetic mean of `ms` over all samples (`0` if empty)
   - `bucket_zero`: count of samples where Euclidean remainder `rem_euclid(offset, 4) == 0` (e.g., `-4 -> 0`, `-5 -> 3`).

### Output JSON Schema
`{"count": int, "breaches": int, "overage_ms": int, "max_ms": int, "mean_ms": int, "bucket_zero": int}`""",

            # Stage 1
            """## Stage 1 — Change 1: Latency Severity Classification

Preserve all Stage 0 behavior and classify each sample's `ms`:
- `< 200` -> `"ok"`
- `<= 500` -> `"warn"`
- `<= 1000` -> `"slow"`
- `else` -> `"critical"`

Add to output JSON:
- `critical`: count of samples classified as `"critical"` (`ms > 1000`)
- `warn_or_worse`: count of samples with `ms >= 200`.

### Output JSON Schema
Add `"critical": int, "warn_or_worse": int` to Stage 0's output JSON.""",

            # Stage 2
            """## Stage 2 — Change 2: Consecutive Breaches & Latency Spikes

Preserve all Stage 0–1 behavior and add two ordered sequence metrics:
1. `consecutive_breaches`: count of adjacent pairs `(past, now)` in `samples` where BOTH breach SLA.
2. `spike_steps`: count of adjacent pairs `(past, now)` in `samples` where `now.ms > past.ms + 100`.

### Output JSON Schema
Add `"consecutive_breaches": int, "spike_steps": int` to Stage 1's output JSON.""",

            # Stage 3
            """## Stage 3 — Change 3: Unicode Service Label Validation

Preserve all Stage 0–2 behavior and add:
1. A normalized `service` name is valid iff its **Unicode codepoint count** (NOT UTF-8 bytes and NOT UTF-16 code units! E.g. `"🔥"` has 1 codepoint -> invalid; `"ok🔥"` has 3 codepoints -> valid) is between `2` and `12` inclusive.
2. `invalid_labels`: count of samples whose normalized service name is invalid.
3. Update `mean_ms` to compute the banker's half-to-even rounded mean over **valid-label samples only** (`0` if no sample has a valid label). All other metrics (`count`, `breaches`, `overage_ms`, `max_ms`, `bucket_zero`, `critical`, `warn_or_worse`, `consecutive_breaches`, `spike_steps`) still cover all samples.

### Output JSON Schema
Add `"invalid_labels": int` to Stage 2's output JSON.""",

            # Stage 4
            """## Stage 4 — Change 4: Maintenance-Window Exemption

Preserve all Stage 0–3 behavior and add:
1. A sample is **exempt** from SLA breach if its normalized service name is `"healthcheck"` AND its Euclidean bucket `rem_euclid(offset, 4) == 0`.
2. Exempt samples do NOT count as breaches (they are excluded from `breaches`, `overage_ms`, and `consecutive_breaches`).
3. `exempt`: count of samples whose raw `ms > sla_ms` but were exempted by this rule.
4. `count`, `max_ms`, `mean_ms`, `bucket_zero`, `critical`, `warn_or_worse`, `spike_steps`, and `invalid_labels` MUST remain unchanged.

### Output JSON Schema
Add `"exempt": int` to Stage 3's output JSON.""",

            # Stage 5
            """## Stage 5 — Change 5: Earlier-Minimum Regression & Overall Status

Preserve all Stage 0–4 behavior and add:
1. `regressed`: count of positions `i` in `samples` (`i > 0`) for which there exists at least one earlier sample `j < i` with `samples[j].ms + 300 < samples[i].ms`.
2. `status`:
   - `"red"` if `consecutive_breaches >= 2` or `critical > 0`
   - else `"yellow"` if `breaches > 0` or `invalid_labels > 0`
   - else `"green"`.

### Output JSON Schema
Add `"regressed": int, "status": string` to Stage 4's output JSON.""",
        ],
    },

    "T3_freight_quote": {
        "title": "Cross-Border Freight Quote Engine",
        "b_required_ecosystems": ("net", "js", "go"),
        "b_ecosystem_note": (
            "In B, compose libraries from all 3 ecosystems: "
            ".NET (`use net:System.Math as NetMath`, `use net:System.Text.RegularExpressions.Regex as Rx`), "
            "Node/npm (`use js:\"node:path/posix\" as path`), and "
            "Go (`use go:strings as gstr`). "
            "Use B units (`unit m`, `unit km = 1000 m`, `unit g`, `unit kg = 1000 g`), currencies (`currency EUR, SEK`), records, decision tables, summaries, and ordered history counts."
        ),
        "oracle": oracle_t3,
        "public": _t3_public,
        "hidden": _t3_hidden,
        "stages": [
            # Stage 0
            """## Stage 0 — Build From Empty File: Cross-Border Freight Quote Engine

Read a JSON object from stdin and print one JSON object to stdout.

### Input JSON Schema
```json
{"eur_to_sek": 11.5, "legs": [{"route": "hub//se/sto-01", "dx_km": 30.0, "dy_km": 40.0, "weight_g": 2500.0, "zone": " eu "}]}
```

### Rules
1. Normalize `route` as a POSIX path and extract `depot = basename(norm)`.
2. Normalize `zone` by trimming whitespace and uppercasing.
3. A leg is **valid** iff `depot` matches regex `^[a-z]{3}-[0-9]{2}$` AND `zone` is one of `"SE"`, `"EU"`, `"NON-EU"`. Invalid legs are ignored in distance/fee totals.
4. For each valid leg:
   - Straight-line distance `km = sqrt(dx_km * dx_km + dy_km * dy_km)` (in km).
   - Weight `kg = weight_g / 1000.0` (convert g to kg; in B use `unit g; unit kg = 1000 g` and `unit m; unit km = 1000 m`).
   - Base leg fee in EUR: `leg_eur = 5.0 + 0.5 * km + 2.0 * kg` (in B use `currency EUR, SEK`).
5. Aggregate over valid legs (`0` if none):
   - `legs`: total input legs
   - `valid_legs`: number of valid legs
   - `total_m`: banker's half-to-even rounded integer of total valid distance in meters (`sum(km) * 1000.0`)
   - `total_eur_cents`: banker's half-to-even rounded integer of `total_eur * 100.0`
   - `total_sek`: banker's half-to-even rounded integer of `total_eur * eur_to_sek`.

### Output JSON Schema
`{"legs": int, "valid_legs": int, "total_m": int, "total_eur_cents": int, "total_sek": int}`""",

            # Stage 1
            """## Stage 1 — Change 1: Distance Multiplier & Heavy Surcharge

Preserve all Stage 0 behavior and update each valid leg's EUR fee:
1. Multiply the Stage 0 base fee (`5.0 + 0.5 * km + 2.0 * kg`) by a distance tier multiplier:
   - `km <= 50.0` -> `1.0`
   - `km <= 200.0` -> `1.15`
   - `else` -> `1.35`
2. If `kg >= 10.0`, add a heavy surcharge of `+12.0` EUR (after the distance multiplier).
3. Add `"heavy_legs": int` (count of valid legs with `kg >= 10.0`) to the output JSON.

### Output JSON Schema
Add `"heavy_legs": int` to Stage 0's output JSON.""",

            # Stage 2
            """## Stage 2 — Change 2: Zone Discount & Customs Fee

Preserve all Stage 0–1 behavior and apply zone adjustments to each valid leg's fee (after Stage 1 multiplier and heavy surcharge):
- `"SE"` -> multiply fee by `0.9` (10% domestic discount)
- `"EU"` -> unchanged
- `"NON-EU"` -> add `+15.0` EUR customs fee

Add `"customs_legs": int` (count of valid `"NON-EU"` legs) to the output JSON.

### Output JSON Schema
Add `"customs_legs": int` to Stage 1's output JSON.""",

            # Stage 3
            """## Stage 3 — Change 3: Consecutive Long-Haul Rest Fee

Preserve all Stage 0–2 behavior and add:
1. Among the sequence of **valid legs** (in input order, skipping invalid legs), count `long_haul_pairs`: adjacent pairs `(prev, curr)` of valid legs where BOTH have `km > 100.0`.
2. Add a rest fee of `25.0 * long_haul_pairs` EUR to `total_eur` (before computing `total_eur_cents` and `total_sek`).

### Output JSON Schema
Add `"long_haul_pairs": int` to Stage 2's output JSON.""",

            # Stage 4
            """## Stage 4 — Change 4: VIP Domestic Depot Exemption

Preserve all Stage 0–3 behavior and add:
1. Valid legs with `depot == "sto-01"` AND `zone == "SE"` are **exempt from the `+12.0` EUR heavy surcharge** (they still receive the 10% `"SE"` discount on their distance-multiplied base fee).
2. `vip_exempt`: count of valid legs with `depot == "sto-01"`, `zone == "SE"`, and `kg >= 10.0`.
3. `heavy_legs`, `valid_legs`, `total_m`, `customs_legs`, and `long_haul_pairs` MUST remain unchanged.

### Output JSON Schema
Add `"vip_exempt": int` to Stage 3's output JSON.""",

            # Stage 5
            """## Stage 5 — Change 5: Budget Cap & Maximum Leg Fee

Preserve all Stage 0–4 behavior and update input/output:
1. Input JSON now includes `"max_sek": int`.
2. Compute:
   - `within_cap`: `true` if `total_sek <= max_sek`, else `false`
   - `max_leg_eur_cents`: maximum over valid legs of `round_even(leg_eur * 100.0)` (`0` if no valid legs; excludes the batch-level `rest_fee`).

### Output JSON Schema
Add `"within_cap": bool, "max_leg_eur_cents": int` to Stage 4's output JSON.""",
        ],
    },
}


def render_stage_md(task_id: str, stage: int, lang: str) -> str:
    task = TASKS[task_id]
    parts = [f"# Task: {task['title']} (`{task_id}`) — Stage {stage}/5\n"]
    if lang == "B":
        parts.append(f"**Ecosystem Requirement (B):** {task['b_ecosystem_note']}\n")
    else:
        parts.append(f"**Language:** {lang} (solve idiomatically using standard {lang} libraries/ecosystem).\n")
    parts.append(task["stages"][stage])
    parts.append("\n## Public Examples (2 smoke checks)\n")
    for idx, inp in enumerate(task["public"](stage), start=1):
        exp = task["oracle"](stage, inp)
        import json
        parts.append(f"### Example {idx}\n**Input:**\n```json\n{json.dumps(inp)}\n```\n**Expected Output:**\n```json\n{json.dumps(exp)}\n```\n")
    return "\n".join(parts)


if __name__ == "__main__":
    # Sanity self-test of all 3 tasks x 6 stages oracles
    total_cases = 0
    for tid, t in TASKS.items():
        for st in range(6):
            pub = t["public"](st)
            hid = t["hidden"](st)
            assert len(pub) == 2
            assert len(hid) == 10
            for x in pub + hid:
                res = t["oracle"](st, x)
                assert isinstance(res, dict)
            total_cases += len(hid)
    print(f"All 3 tasks x 6 stages verified cleanly ({total_cases} hidden oracle cases).")
