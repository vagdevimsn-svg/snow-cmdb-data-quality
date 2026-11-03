# CMDB Data Quality Report

- CIs evaluated: **11**
- Health score: **59.1 / 100**
- Findings: **14**

## Score by class

| Class | CIs | Score |
|---|---|---|
| cmdb_ci_server | 5 | 36.7 |
| cmdb_ci_service_auto | 2 | 50.0 |
| cmdb_ci_appl | 2 | 83.3 |
| cmdb_ci_business_app | 1 | 100.0 |
| cmdb_ci_db_instance | 1 | 100.0 |

## Findings by check

| Check | Count |
|---|---|
| missing_field | 3 |
| orphan | 3 |
| duplicate | 2 |
| stale | 1 |
| never_discovered | 1 |
| empty_service | 1 |
| service_without_business_app | 1 |
| retired_in_use | 1 |
| dangling_relationship | 1 |

## Detail

| Severity | Check | CI | Class | Detail | Remediation |
|---|---|---|---|---|---|
| high | duplicate | LNX-PAY-02 | cmdb_ci_server | duplicate on serial with: srv002 | Review IRE identification rules; merge or retire the duplicate CI |
| high | duplicate | lnx-pay-02 | cmdb_ci_server | duplicate on serial with: srv003 | Review IRE identification rules; merge or retire the duplicate CI |
| high | empty_service | Branch Reporting | cmdb_ci_service_auto | application service has no downstream dependencies mapped | Run Service Mapping or build the service from tags/dynamic CI groups |
| high | never_discovered | win-rpt-01 | cmdb_ci_server | operational CI has no last_discovered date | Add the CI's IP range to a Discovery schedule or confirm it is manually managed |
| high | retired_in_use | win-old-09 | cmdb_ci_server | retired but still a dependency of ledger-batch | Remove the relationship or correct install_status |
| medium | missing_field | Branch Reporting | cmdb_ci_service_auto | 'owned_by' is empty | Populate owned_by (owner/support data drives assignment and impact) |
| medium | missing_field | ledger-batch | cmdb_ci_appl | 'support_group' is empty | Populate support_group (owner/support data drives assignment and impact) |
| medium | missing_field | win-rpt-01 | cmdb_ci_server | 'ip_address' is empty | Populate ip_address (owner/support data drives assignment and impact) |
| medium | orphan | Branch Reporting | cmdb_ci_service_auto | no cmdb_rel_ci relationships | Map the CI with Service Mapping or add a Runs on / Depends on relationship |
| medium | orphan | LNX-PAY-02 | cmdb_ci_server | no cmdb_rel_ci relationships | Map the CI with Service Mapping or add a Runs on / Depends on relationship |
| medium | orphan | win-rpt-01 | cmdb_ci_server | no cmdb_rel_ci relationships | Map the CI with Service Mapping or add a Runs on / Depends on relationship |
| medium | service_without_business_app | Branch Reporting | cmdb_ci_service_auto | no business application consumes this service | Link the service to its cmdb_ci_business_app (Consumes::Consumed by) |
| medium | stale | lnx-pay-02 | cmdb_ci_server | last discovered 125 days ago (> 30) | Check Discovery schedule, MID Server reachability and credentials; retire if decommissioned |
| low | dangling_relationship | rel5 | cmdb_rel_ci | child srv999 does not exist | Delete the relationship or restore the missing CI |
