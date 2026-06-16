/**
 * consumer-backend-startup.js — Bootstrap patch for the Express consumer backend
 *
 * SECRET NAME: thinkvelocity/production/consumer-backend
 * SERVICE PORT: 3005
 *
 * PURPOSE
 * -------
 * Secrets must be in process.env before Express initialises any modules that
 * read env vars at require()-time (database pools, Redis clients, JWT helpers,
 * Razorpay SDK, SendGrid, Sentry, etc.).  This file is the NEW entry point.
 * It calls initSecrets() first, then delegates to the original server file.
 *
 * HOW TO INTEGRATE
 * ----------------
 * 1. Copy secrets-loader.js next to your entry point (or install it as a
 *    shared internal package — see DEPLOY_INSTRUCTIONS.md).
 *
 * 2. Rename your current entry point (e.g. server.js → server.core.js).
 *    Or — if you prefer zero-rename — just prepend the initSecrets block to
 *    the top of your existing entry point and skip the require() at the bottom.
 *
 * 3. Update your Dockerfile CMD / package.json "start" script to point to
 *    THIS file instead of the original entry point:
 *
 *      # Dockerfile
 *      CMD ["node", "consumer-backend-startup.js"]
 *
 *      # package.json
 *      "scripts": { "start": "node consumer-backend-startup.js" }
 *
 * 4. For local dev, create a .env file in the project root and load it with
 *    dotenv BEFORE calling initSecrets (dotenv is a no-op in production since
 *    .env files are not present in the Docker image):
 *
 *      require('dotenv').config();   // loads .env if present, harmless if not
 *      const { initSecrets } = require('./secrets-loader');
 *      ...
 *
 * LOCAL DEV BEHAVIOUR
 * -------------------
 * If AWS_REGION is not set in the environment, secrets-loader skips Secrets
 * Manager entirely.  All configuration is sourced from the local .env file
 * (loaded via dotenv above) or from environment variables in the shell.
 * No AWS credentials or network access are needed for local development.
 */

'use strict';

// ---------------------------------------------------------------------------
// Step 1 — Load .env for local dev (dotenv silently ignores missing files)
// ---------------------------------------------------------------------------
// In production the Docker image does NOT include a .env file, so this line
// is effectively a no-op there.  Install dotenv as a dev dependency:
//   npm install --save-dev dotenv
// ---------------------------------------------------------------------------
try {
  require('dotenv').config();
} catch (_) {
  // dotenv not installed — fine in production; env vars come from SM / Docker
}

// ---------------------------------------------------------------------------
// Step 2 — Fetch secrets from AWS Secrets Manager BEFORE anything else loads
// ---------------------------------------------------------------------------
const { initSecrets } = require('./secrets-loader');

const SECRET_NAME = 'thinkvelocity/production/consumer-backend';

async function bootstrap() {
  // Populate process.env from Secrets Manager (or skip gracefully if local dev)
  await initSecrets(SECRET_NAME);

  // ---------------------------------------------------------------------------
  // Step 3 — NOW safe to require modules that read env vars at import time
  // ---------------------------------------------------------------------------
  // Replace the line below with the actual path to your Express app entry point.
  // Common names: server.js, app.js, index.js, src/index.js
  // ---------------------------------------------------------------------------
  const app = require('./server'); // <-- adjust path to your Express entry point

  // If your entry point already calls app.listen() internally, you are done.
  // If it exports the app without listening, start the server here:
  //
  // const PORT = process.env.PORT || 3005;
  // app.listen(PORT, () => {
  //   console.log(`[consumer-backend] Listening on port ${PORT}`);
  // });
}

bootstrap().catch((err) => {
  console.error('[consumer-backend] Fatal error during startup:', err);
  process.exit(1);
});
