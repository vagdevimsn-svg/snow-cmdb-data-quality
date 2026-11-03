# Security

- The tool only issues `GET` requests to `cmdb_ci` and `cmdb_rel_ci`. Use a dedicated integration account with read-only CMDB access.
- Credentials are read from environment variables (`SN_USER`/`SN_PASSWORD` or `SN_TOKEN`) and are never logged or written to reports.
- `https` is enforced. Plain `http` is accepted only for localhost or when `SN_ALLOW_INSECURE_HTTP=true` is set for the bundled mock server.
- Reports can contain CI names and support groups from your instance; treat them as internal data.
- All data in this repository is synthetic.

Report a security issue by opening a private GitHub security advisory on this repository.
