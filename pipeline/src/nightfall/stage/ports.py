from __future__ import annotations

from nightfall.core.lake import Lake
from nightfall.stage.common import available_on, make_table, num, parse_date

CLASSES = ("container", "dry_bulk", "general_cargo", "roro", "tanker")


def stage_ports(lake: Lake):
    rows = {}
    for rec in lake.iter_raw("portwatch", "ports"):
        for r in rec["payload"]:
            rows[r["portid"]] = {
                "portid": r["portid"],
                "name": r["portname"],
                "lat": num(r["lat"]),
                "lon": num(r["lon"]),
                "vessel_count_total": num(r.get("vessel_count_total")),
            }
    cols = {"portid": "str", "name": "str", "lat": "f", "lon": "f", "vessel_count_total": "f"}

    daily = {}
    for rec in lake.iter_raw("portwatch", "daily_ports"):
        for r in rec["payload"]:
            d = parse_date(str(r["date"]))
            daily[(r["portid"], d)] = {
                "date": d,
                "portid": r["portid"],
                "calls": num(r.get("portcalls")),
                "calls_container": num(r.get("portcalls_container")),
                "calls_tanker": num(r.get("portcalls_tanker")),
                "calls_dry_bulk": num(r.get("portcalls_dry_bulk")),
                "calls_general_cargo": num(r.get("portcalls_general_cargo")),
                "calls_roro": num(r.get("portcalls_roro")),
                "import_t": num(r.get("import")),
                "export_t": num(r.get("export")),
                **{f"import_{k}_t": num(r.get(f"import_{k}")) for k in CLASSES},
                **{f"export_{k}_t": num(r.get(f"export_{k}")) for k in CLASSES},
                "available_on": available_on(d, "portwatch"),
            }
    dcols = {
        "date": "date",
        "portid": "str",
        "calls": "f",
        "calls_container": "f",
        "calls_tanker": "f",
        "calls_dry_bulk": "f",
        "calls_general_cargo": "f",
        "calls_roro": "f",
        "import_t": "f",
        "export_t": "f",
        **{f"import_{k}_t": "f" for k in CLASSES},
        **{f"export_{k}_t": "f" for k in CLASSES},
        "available_on": "date",
    }

    choke = {}
    for rec in lake.iter_raw("portwatch", "daily_chokepoints"):
        for r in rec["payload"]:
            d = parse_date(str(r["date"]))
            choke[(r["portid"], d)] = {
                "date": d,
                "chokepoint_id": r["portid"],
                "name": r["portname"],
                "n_total": num(r.get("n_total")),
                "n_container": num(r.get("n_container")),
                "n_dry_bulk": num(r.get("n_dry_bulk")),
                "n_tanker": num(r.get("n_tanker")),
                "n_roro": num(r.get("n_roro")),
                "capacity": num(r.get("capacity")),
                "available_on": available_on(d, "portwatch"),
            }
    ccols = {
        "date": "date",
        "chokepoint_id": "str",
        "name": "str",
        "n_total": "f",
        "n_container": "f",
        "n_dry_bulk": "f",
        "n_tanker": "f",
        "n_roro": "f",
        "capacity": "f",
        "available_on": "date",
    }
    return {
        "port_ref": make_table(sorted(rows.values(), key=lambda x: x["portid"]), cols),
        "port_daily": make_table(sorted(daily.values(), key=lambda x: (x["portid"], x["date"])), dcols),
        "chokepoint_daily": make_table(
            sorted(choke.values(), key=lambda x: (x["chokepoint_id"], x["date"])), ccols
        ),
    }
