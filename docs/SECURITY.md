# Security

## Do Not Commit

- Broker credentials (MT5 login/password/server)
- Tokens/keys (Telegram, GitHub, news APIs)
- Any `.env*`, vault/keystore files, private keys/certs (`*.key`, `*.pem`, `*.pfx`, `*.p12`)
- Databases (`*.sqlite`, `*.db`) and user logs

## Storage

- Put secrets only in local machine secret storage (Windows Credential Manager) or encrypted vault files outside the repo.
- Keep persistent runtime data in `C:\ProgramData\GodTierBot\` (never under the git repo).

## Support Bundles

- Support bundles must be sanitized (tokens/passwords removed) before sharing.
