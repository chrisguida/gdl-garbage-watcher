# gdl-garbage-watcher

Live map of Guadalajara's CAABSA garbage trucks, pulled from the city's public
[`/caabsa/posiciones`](https://tequierolimpiapi.guadalajara.gob.mx/caabsa/posiciones)
feed. Click anywhere on the map to drop a pin; if you grant notification
permission, the browser will alert you when any truck enters 150 m of it.

The pin is stored in `localStorage` only — never sent anywhere.

## Why a proxy

The upstream API uses HTTPS but the certificate expired in August 2025, so
browsers refuse to fetch it directly. A small server-side proxy fetches over
HTTPS with cert validation disabled, so transport encryption is preserved
even though we can't verify the cert.

## Local development

```bash
python3 serve.py        # serves index.html and proxies /api/posiciones on :8765
```

Open http://localhost:8765/.

## Deploy (Vercel)

1. Push this repo to GitHub.
2. Import the repo at https://vercel.com/new.
3. Vercel detects `api/posiciones.js` automatically — no extra config needed.

The static `index.html` is served at `/`; the proxy is at `/api/posiciones`.
