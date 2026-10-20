# SuperDeal PC Backend

SuperDeal can run its API and SQLite database on your Windows PC while the Android app connects over your home LAN.

## 1. Start the API

Double-click:

`scripts\\start_superdeal_api.bat`

The server listens on port `8000` and binds to `0.0.0.0` for LAN access. The database remains local at `data\\superdeal.db`.

## 2. Find the PC address

On the PC, run:

```text
ipconfig
```

Find the active adapter's IPv4 address, for example `192.168.1.10`.

From another device on the same network, the API health endpoint is:

`http://192.168.1.10:8000/health`

It should return JSON containing `"status": "ok"`.

## 3. Windows Firewall

If the phone cannot reach the API, allow inbound TCP port `8000` for the private/home network in Windows Defender Firewall. Do not expose port 8000 directly to the public internet.

## 4. Android app

The app needs the PC API address as its API base URL. The intended production flow is a one-time in-app connection screen, storing the LAN API address locally on the phone. Until that UI is wired into the APK, do not hard-code a guessed IP address because home-network addresses can change.

## Architecture

```text
Telegram / web ingestion
          |
          v
     Windows PC
  +----------------+
  | Worker         |
  | Parser         |
  | Enrichment     |
  | SQLite         |
  | REST API :8000 |
  +-------+--------+
          |
       Wi-Fi/LAN
          |
          v
     Android App
```

The API is deliberately separated from the Android UI so the database, parsing, scraping and workers remain on the PC.
