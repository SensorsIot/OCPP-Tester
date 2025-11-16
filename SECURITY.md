# Security Policy

## Overview

This repository implements multiple layers of security to prevent accidental exposure of sensitive data.

## Security Measures in Place

### 1. Pre-Commit Hook (Automatic Secret Scanning)

A pre-commit hook automatically scans all files before every commit to detect:

- **GitHub Tokens**: Personal Access Tokens (PAT), OAuth tokens, refresh tokens
- **SSH Private Keys**: RSA, ECDSA, Ed25519 private keys
- **AWS Credentials**: Access keys and secret keys
- **API Keys and Secrets**: Generic API keys, passwords, secrets in configuration
- **Sensitive Files**: `.env`, `credentials.json`, SSH keys, certificates

**Location**: `.git/hooks/pre-commit`

**Bypass** (only if you're sure it's a false positive):
```bash
git commit --no-verify
```

### 2. Comprehensive .gitignore

The `.gitignore` file prevents sensitive files from being tracked:

**Security Patterns**:
- SSH Keys: `id_rsa*`, `id_ed25519*`, `id_ecdsa*`, `*.pem`, `*.key`
- Certificates: `*.p12`, `*.pfx`
- Environment Files: `.env`, `.env.*`, `*.secrets`
- Credentials: `.git-credentials`, `.netrc`, `credentials.json`
- Secrets: `secrets.yaml`, `secrets.yml`

### 3. SSH Authentication (No Tokens in Git Config)

The repository uses SSH key authentication instead of HTTPS tokens:

- Remote URL: `git@github.com:SensorsIot/OCPP-Tester.git`
- No credentials stored in git config
- Credential helper disabled

### 4. Git History Cleaned

All sensitive data has been permanently removed from git history:
- SSH private keys purged from all commits
- Repository history rewritten and force-pushed

## Best Practices

### Never Commit:

1. ❌ SSH private keys (`id_rsa`, `id_ed25519`, etc.)
2. ❌ GitHub Personal Access Tokens (starting with `ghp_`, `github_pat_`, etc.)
3. ❌ Environment files (`.env`, `.env.local`, etc.)
4. ❌ Credential files (`credentials.json`, `.git-credentials`, etc.)
5. ❌ Private certificates (`*.pem`, `*.p12`, `*.pfx`)
6. ❌ Passwords or API keys in code

### What to Do If You Accidentally Commit Secrets:

1. **Immediately revoke/regenerate** the exposed credential
2. **Do NOT just delete the file** - it's still in git history
3. Contact repository maintainer to clean git history
4. Update the compromised service with new credentials

### SSH Key Management:

**Generate SSH Key** (if needed):
```bash
ssh-keygen -t ed25519 -C "your_email@example.com"
```

**Add to GitHub**:
1. Copy public key: `cat ~/.ssh/id_ed25519.pub`
2. Go to: https://github.com/settings/keys
3. Add new SSH key

**Never commit**:
- `~/.ssh/id_ed25519` (private key)
- `~/.ssh/id_rsa` (private key)

**You can safely view** (but shouldn't commit):
- `~/.ssh/id_ed25519.pub` (public key)

### Using Environment Variables:

For sensitive configuration, use environment variables:

```bash
# Create .env file (automatically ignored)
echo "OCPP_API_KEY=your-secret-key" > .env
```

In Python:
```python
import os
api_key = os.getenv('OCPP_API_KEY')
```

## Incident Response

If sensitive data is discovered in the repository:

1. **Immediate**: Revoke/regenerate the exposed credential
2. **Contact**: Repository maintainer immediately
3. **Document**: What was exposed, when, and what actions were taken
4. **Remediate**: Clean git history using `git filter-branch` or `git-filter-repo`
5. **Verify**: Confirm credential no longer works and new one is in place

## Security Contacts

- Repository Owner: Andreas Spiess
- Email: andreas.spiess@rumba.com

## Changelog

- **2025-11-16**: Implemented pre-commit hook for secret scanning
- **2025-11-16**: Enhanced .gitignore with comprehensive security patterns
- **2025-11-16**: Removed exposed SSH keys from git history
- **2025-09-22**: Added initial .gitignore for .ssh directory

---

Last Updated: 2025-11-16
