// Vercel serverless function that proxies the Guadalajara CAABSA truck-positions
// API. The upstream serves HTTPS but its TLS cert is expired, so we keep
// transport encryption while skipping certificate validation.

const https = require('node:https');

const UPSTREAM = 'https://tequierolimpiapi.guadalajara.gob.mx/caabsa/posiciones';

module.exports = async (req, res) => {
  try {
    const body = await new Promise((resolve, reject) => {
      const r = https.get(
        UPSTREAM,
        {
          rejectUnauthorized: false,
          headers: { 'User-Agent': 'gdl-garbage-watcher proxy' },
          timeout: 12000,
        },
        (up) => {
          if (up.statusCode !== 200) {
            reject(new Error(`upstream ${up.statusCode}`));
            up.resume();
            return;
          }
          const chunks = [];
          up.on('data', (c) => chunks.push(c));
          up.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
        }
      );
      r.on('timeout', () => r.destroy(new Error('upstream timeout')));
      r.on('error', reject);
    });
    res.setHeader('Content-Type', 'application/json');
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.status(200).send(body);
  } catch (e) {
    res.status(502).json({ error: String(e.message || e) });
  }
};
