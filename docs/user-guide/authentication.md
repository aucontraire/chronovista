# Authentication

Guide to authenticating chronovista with your YouTube account.

## Overview

chronovista uses OAuth 2.0 to securely access your YouTube data. This grants the application permission to read your watch history, playlists, subscriptions, and other account data.

## Quick Start

```bash
# Login to your YouTube account
chronovista auth login

# Check authentication status
chronovista auth status

# Logout when done
chronovista auth logout
```

## Authentication Flow

### Step 1: Initiate Login

```bash
chronovista auth login
```

This command:

1. Opens your default browser
2. Redirects to Google's OAuth consent page
3. Starts a local callback server on port 8080

### Step 2: Grant Permissions

In your browser, you'll see Google's consent screen:

1. Select your Google account
2. Review the requested permissions
3. Click "Allow" to grant access

!!! info "Requested Permissions"
    chronovista requests read-only access by default:

    - View your YouTube account
    - View your YouTube playlists and subscriptions
    - View your YouTube watch history

### Step 3: Callback

After granting permission:

1. Google redirects to `http://localhost:8080/auth/callback`
2. chronovista receives the authorization code
3. The code is exchanged for access tokens
4. Tokens are securely stored locally

### Step 4: Verification

```bash
chronovista auth status
```

Output:
```
Authentication Status
---------------------
Status: Authenticated
Account: your-email@gmail.com
Token Expires: 2024-01-15 14:30:00
Scopes: youtube.readonly
```

## Credential Storage

OAuth tokens are stored securely in your home directory:

```
~/.chronovista/
└── credentials/
    └── youtube_token.json
```

!!! warning "Security"
    - Tokens are stored locally on your machine
    - Never share your credential files
    - The token file is excluded from version control

## Token Management

### Token Refresh

Access tokens expire after 1 hour. chronovista automatically refreshes them using the refresh token when needed.

### Force Re-authentication

If you encounter authentication issues:

```bash
chronovista auth login --force
```

This clears existing credentials and starts a fresh authentication flow.

### Logout

To remove stored credentials:

```bash
chronovista auth logout
```

This deletes the token file and revokes the session.

## OAuth Scopes

### Read Scopes (Default)

| Scope | Purpose |
|-------|---------|
| `youtube.readonly` | Read account data |
| `youtube.force-ssl` | Secure API connections |

### Write Scopes (Phase 3)

Additional scopes for write operations:

| Scope | Purpose |
|-------|---------|
| `youtube` | Full account access |
| `youtube.upload` | Upload videos |

## Troubleshooting

### Browser Doesn't Open

If the browser doesn't open automatically:

1. Copy the URL from the terminal
2. Paste it into your browser manually

### Port 8080 In Use

If port 8080 is busy:

```bash
# Find what's using the port
lsof -i :8080

# Kill the process if safe
kill -9 <PID>

# Or use a different port
chronovista auth login --port 8081
```

### Token Expired

If you see "Token expired" errors:

```bash
# This will auto-refresh
chronovista auth status

# Or force new login
chronovista auth login --force
```

### Invalid Credentials

If you get "Invalid credentials" errors:

1. Verify your OAuth client ID and secret in `.env`
2. Ensure redirect URI matches: `http://localhost:8080/auth/callback`
3. Check that YouTube Data API v3 is enabled in Google Cloud Console

### Consent Screen Not Appearing

If redirected to an error page:

1. Check that your OAuth consent screen is configured
2. Verify the application is in "Testing" or "Production" mode
3. Add your email as a test user if in Testing mode

## Security Best Practices

!!! tip "Security Recommendations"

    1. **Use a dedicated Google account** for testing if concerned about privacy
    2. **Review permissions** carefully before granting access
    3. **Logout** when not using the application
    4. **Rotate credentials** periodically

### Revoking Access

To fully revoke chronovista's access:

1. Go to [Google Account Security](https://myaccount.google.com/permissions)
2. Find "chronovista" in the list
3. Click "Remove Access"
4. Run `chronovista auth logout` locally

## Multiple Accounts

Currently, chronovista supports one authenticated account at a time. To switch accounts:

```bash
# Logout from current account
chronovista auth logout

# Login with different account
chronovista auth login
```

## API Quotas

Authentication is required to make API calls. Be aware of quotas:

| Resource | Daily Limit |
|----------|-------------|
| Queries | 10,000 units |
| Videos list | 1 unit each |
| Captions download | 200 units each |

!!! note "Quota Management"
    chronovista implements rate limiting and caching to minimize quota usage. If you hit quota limits, wait 24 hours for reset.

## See Also

- [Configuration](../getting-started/configuration.md) - OAuth settings
- [CLI Overview](cli-overview.md) - All commands
- [Transcripts](transcripts.md) - Caption download limits
