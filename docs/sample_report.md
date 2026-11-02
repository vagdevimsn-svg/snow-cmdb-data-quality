# CMDB Data Quality Report

- CIs evaluated: **10**
- Health score: **60.0 / 100**
- Findings: **12**

## Findings by check

| Check | Count |
|---|---|
| missing_field | 3 |
| orphan | 3 |
| duplicate | 2 |
| stale | 1 |
| never_discovered | 1 |
| empty_service | 1 |
| dangling_relationship | 1 |

## Detail

| Severity | Check | CI | Class | Detail |
|---|---|---|---|---|
| high | duplicate | LNX-PAY-02 | cmdb_ci_server | duplicate on serial with 1 other CI(s): srv002 |
| high | duplicate | lnx-pay-02 | cmdb_ci_server | duplicate on serial with 1 other CI(s): srv003 |
| high | empty_service | Branch Reporting | cmdb_ci_service_auto | application service has no downstream dependencies mapped |
| high | never_discovered | win-rpt-01 | cmdb_ci_server | operational CI has no last_discovered date |
| medium | missing_field | Branch Reporting | cmdb_ci_service_auto | 'owned_by' is empty |
| medium | missing_field | ledger-batch | cmdb_ci_appl | 'support_group' is empty |
| medium | missing_field | win-rpt-01 | cmdb_ci_server | 'ip_address' is empty |
| medium | orphan | Branch Reporting | cmdb_ci_service_auto | no cmdb_rel_ci relationships |
| medium | orphan | LNX-PAY-02 | cmdb_ci_server | no cmdb_rel_ci relationships |
| medium | orphan | win-rpt-01 | cmdb_ci_server | no cmdb_rel_ci relationships |
| medium | stale | lnx-pay-02 | cmdb_ci_server | last discovered 124 days ago (> 30) |
| low | dangling_relationship | rel5 | cmdb_rel_ci | child srv999 does not exist |

