"""Generates a small synthetic CMDB export. All names, IPs and serials are fictitious."""
import json
from pathlib import Path


def ci(sys_id, name, cls, **kw):
    base = {"sys_id": sys_id, "name": name, "sys_class_name": cls, "install_status": "1"}
    base.update(kw)
    return base


cis = [
    ci("bapp01", "Digital Payments", "cmdb_ci_business_app", owned_by="u_owner1", it_application_owner="u_itown1"),
    ci("svc001", "Online Payments", "cmdb_ci_service_auto", owned_by="u_owner1", support_group="grp_pay",
       busines_criticality="1 - most critical"),
    ci("svc002", "Branch Reporting", "cmdb_ci_service_auto", owned_by="", support_group="grp_rpt",
       busines_criticality="3 - less critical"),
    ci("app001", "payments-api", "cmdb_ci_appl", owned_by="u_owner1", support_group="grp_pay"),
    ci("app002", "ledger-batch", "cmdb_ci_appl", owned_by="u_owner2", support_group=""),
    ci("srv001", "lnx-pay-01", "cmdb_ci_server", serial_number="SYN-0001", ip_address="10.0.0.11",
       os="Linux Red Hat", support_group="grp_unix", last_discovered="2026-10-30 04:00:00"),
    ci("srv002", "lnx-pay-02", "cmdb_ci_server", serial_number="SYN-0002", ip_address="10.0.0.12",
       os="Linux Red Hat", support_group="grp_unix", last_discovered="2026-07-01 04:00:00"),
    ci("srv003", "LNX-PAY-02", "cmdb_ci_server", serial_number="syn-0002", ip_address="10.0.0.12",
       os="Linux Red Hat", support_group="grp_unix", last_discovered="2026-10-29 04:00:00"),
    ci("srv004", "win-rpt-01", "cmdb_ci_server", serial_number="SYN-0004", ip_address="", os="Windows 2022",
       support_group="grp_win", last_discovered=""),
    ci("srv005", "win-old-09", "cmdb_ci_server", serial_number="SYN-0009", ip_address="10.0.9.9",
       os="Windows 2012", support_group="grp_win", install_status="7", last_discovered="2024-01-01 00:00:00"),
    ci("db001", "PAYDB01", "cmdb_ci_db_instance", support_group="grp_dba", last_discovered="2026-10-30 05:00:00"),
]
rels = [
    {"sys_id": "rel0", "parent": "bapp01", "child": "svc001", "type": "Consumes::Consumed by"},
    {"sys_id": "rel1", "parent": "svc001", "child": "app001", "type": "Depends on::Used by"},
    {"sys_id": "rel2", "parent": "app001", "child": "srv001", "type": "Runs on::Runs"},
    {"sys_id": "rel3", "parent": "app001", "child": "srv002", "type": "Runs on::Runs"},
    {"sys_id": "rel4", "parent": "app001", "child": "db001", "type": "Depends on::Used by"},
    {"sys_id": "rel5", "parent": "app002", "child": "srv999", "type": "Runs on::Runs"},
    {"sys_id": "rel6", "parent": "app002", "child": "srv005", "type": "Runs on::Runs"},
]
out = Path(__file__).with_name("cmdb_export.json")
out.write_text(json.dumps({"cmdb_ci": cis, "cmdb_rel_ci": rels}, indent=2) + "\n")
print(f"wrote {out}")
