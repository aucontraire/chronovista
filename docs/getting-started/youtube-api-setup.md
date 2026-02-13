# YouTube API Setup

Step-by-step guide to configuring Google Cloud credentials for chronovista.

## Overview

chronovista requires two types of Google Cloud credentials:

| Credential | Purpose | Required? |
|------------|---------|-----------|
| **API Key** | Unauthenticated API calls (video metadata, search) | Yes |
| **OAuth 2.0 Client ID** | Authenticated access (your watch history, playlists, subscriptions) | Yes |

!!! info "Free Tier"
    The YouTube Data API v3 is free within its quota limits (10,000 units/day). No billing account is required for typical personal use.

## Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click the project dropdown at the top of the page
3. Click **New Project**
4. Enter a project name (e.g., `chronovista`)
5. Click **Create**

## Step 2: Enable the YouTube Data API

1. In your project, navigate to **APIs & Services** > **Library**
2. Search for **YouTube Data API v3**
3. Click on it, then click **Enable**

## Step 3: Configure the OAuth Consent Screen

!!! warning "Do This Before Creating Credentials"
    You **must** configure the OAuth consent screen before you can create OAuth credentials. Skipping this step is the most common cause of authentication failures.

1. Navigate to **APIs & Services** > **OAuth consent screen**
2. Select **External** as the user type (unless you have a Google Workspace organization)
3. Click **Create**

Fill in the required fields:

| Field | Value |
|-------|-------|
| **App name** | `chronovista` |
| **User support email** | Your email address |
| **Developer contact email** | Your email address |

4. Click **Save and Continue** through the remaining screens (Scopes, Test users, Summary)

### Add Yourself as a Test User

While the app is in **Testing** mode (the default), only explicitly listed test users can authenticate:

1. On the OAuth consent screen page, scroll to **Test users**
2. Click **Add users**
3. Enter your Google account email address
4. Click **Save**

!!! note "Testing vs Production"
    In Testing mode, only listed test users can authenticate. This is fine for personal use. You do not need to publish the app to Production.

## Step 4: Create an API Key

1. Navigate to **APIs & Services** > **Credentials**
2. Click **Create Credentials** > **API key**
3. Copy the generated API key
4. (Recommended) Click **Edit API key** to restrict it:
    - Under **API restrictions**, select **Restrict key**
    - Choose **YouTube Data API v3**
    - Click **Save**

## Step 5: Create OAuth 2.0 Credentials

1. Still on the **Credentials** page, click **Create Credentials** > **OAuth client ID**
2. Select **Desktop application** as the application type
3. Enter a name (e.g., `chronovista-desktop`)
4. Click **Create**

You will see a dialog showing your **Client ID** and **Client Secret**. You can also click **Download JSON** to save these, but note the important detail below.

### Configure the Redirect URI

1. Click on your newly created OAuth client ID to edit it
2. Under **Authorized redirect URIs**, add:
   ```
   http://localhost:8080/auth/callback
   ```
3. Click **Save**

!!! warning "Exact Match Required"
    The redirect URI must exactly match `http://localhost:8080/auth/callback` (including the protocol `http://`, not `https://`).

## Step 6: Add Credentials to .env

chronovista reads credentials from **environment variables**, not from a downloaded JSON file. Copy the values into your `.env` file:

```bash
cp .env.example .env
```

Then edit `.env`:

```env
# YouTube API Configuration
YOUTUBE_API_KEY=AIzaSy...your_api_key_here
YOUTUBE_CLIENT_ID=123456789-abcdefg.apps.googleusercontent.com
YOUTUBE_CLIENT_SECRET=GOCSPX-your_client_secret_here
```

!!! important "Do Not Use the Downloaded JSON Directly"
    Google Cloud Console offers a "Download JSON" button. chronovista does **not** read this JSON file. You need to extract the `client_id` and `client_secret` values from the JSON (or copy them from the console) and paste them into your `.env` file.

## Verify Your Setup

After completing the [Installation](installation.md), verify credentials are configured:

```bash
# Check that the CLI can start
chronovista --version

# Authenticate with YouTube
chronovista auth login
```

The `auth login` command will:

1. Open your browser to Google's consent screen
2. Ask you to authorize chronovista
3. Print a callback URL in the browser that you need to **copy and paste back into the terminal**

See [Authentication](../user-guide/authentication.md) for the full authentication flow.

## Troubleshooting

### "Access blocked: This app's request is invalid"

Your OAuth consent screen is not configured. Go to **APIs & Services** > **OAuth consent screen** and complete the setup (Step 3 above).

### "Error 403: access_denied"

Your Google account is not listed as a test user. Add your email in the OAuth consent screen's **Test users** section (Step 3 above).

### "Error: redirect_uri_mismatch"

The redirect URI in Google Cloud Console does not match the one chronovista uses. Ensure you have added exactly `http://localhost:8080/auth/callback` (Step 5 above).

### "The API key is invalid"

1. Verify `YOUTUBE_API_KEY` in `.env` matches the key in Google Cloud Console
2. Ensure the YouTube Data API v3 is enabled for your project
3. If you restricted the key, ensure YouTube Data API v3 is in the allowed APIs

## See Also

- [Prerequisites](prerequisites.md) - Software requirements
- [Installation](installation.md) - Install chronovista
- [Authentication](../user-guide/authentication.md) - OAuth flow details
