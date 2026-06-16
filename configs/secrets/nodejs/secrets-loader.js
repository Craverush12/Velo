/**
 * secrets-loader.js — AWS Secrets Manager integration for ThinkVelocity Node.js services
 *
 * How it works:
 *   1. At process start, call initSecrets(secretName).
 *   2. If AWS_REGION is set, the module fetches the named secret JSON from
 *      AWS Secrets Manager and merges all key/value pairs into process.env.
 *   3. If AWS_REGION is NOT set (local dev), it skips SM entirely and uses
 *      whatever is already in process.env (populated by dotenv or shell).
 *   4. The fetch result is cached in-memory; subsequent calls are no-ops.
 *
 * Prerequisites (production):
 *   npm install @aws-sdk/client-secrets-manager
 *
 * No AWS credentials are ever hardcoded. The SDK resolves credentials via the
 * EC2 instance's attached IAM role (IMDSv2 metadata endpoint).
 */

'use strict';

const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');

// ---------------------------------------------------------------------------
// In-process cache — ensures a single network call per container lifecycle
// ---------------------------------------------------------------------------
let _loaded = false;
let _secretCache = null;

/**
 * Determines whether the runtime environment is configured for AWS.
 * If AWS_REGION is absent we assume local dev and skip Secrets Manager.
 *
 * @returns {boolean}
 */
function isAwsConfigured() {
  return typeof process.env.AWS_REGION === 'string' && process.env.AWS_REGION.trim() !== '';
}

/**
 * Fetches a secret from AWS Secrets Manager and merges its JSON fields
 * into process.env.  Already-set env vars are NOT overwritten so that
 * a Docker environment block can still take precedence if needed.
 *
 * @param {string} secretName  - Full secret name, e.g.
 *                               "thinkvelocity/production/consumer-backend"
 * @returns {Promise<object>}  - The parsed secret object (also merged into process.env)
 */
async function loadSecrets(secretName) {
  // Return cached result on repeated calls
  if (_loaded) {
    return _secretCache || {};
  }

  // Local dev short-circuit
  if (!isAwsConfigured()) {
    console.log('[secrets-loader] AWS_REGION not set — skipping Secrets Manager (local dev mode)');
    _loaded = true;
    _secretCache = {};
    return {};
  }

  const client = new SecretsManagerClient({ region: process.env.AWS_REGION });

  let secretString;
  try {
    const response = await client.send(
      new GetSecretValueCommand({ SecretId: secretName })
    );
    secretString = response.SecretString;
  } catch (err) {
    // Degraded mode: log the error and continue. The service will use
    // whatever is already in process.env (useful for staged rollouts or
    // transient SM outages — the container is already running after all).
    console.warn(
      `[secrets-loader] WARNING: Failed to fetch secret "${secretName}" from AWS Secrets Manager. ` +
      `Continuing with existing process.env values.\n` +
      `Error: ${err.name}: ${err.message}`
    );
    _loaded = true;
    _secretCache = {};
    return {};
  }

  // Parse the JSON secret
  let secrets;
  try {
    secrets = JSON.parse(secretString);
  } catch (parseErr) {
    console.warn(
      `[secrets-loader] WARNING: Secret "${secretName}" is not valid JSON. ` +
      `Continuing with existing process.env values.\n` +
      `Parse error: ${parseErr.message}`
    );
    _loaded = true;
    _secretCache = {};
    return {};
  }

  // Merge into process.env — do NOT overwrite values already present so that
  // Docker's own "environment:" block (e.g. NODE_ENV, PORT) stays authoritative.
  let injectedCount = 0;
  for (const [key, value] of Object.entries(secrets)) {
    if (process.env[key] === undefined) {
      process.env[key] = String(value);
      injectedCount++;
    }
  }

  console.log(
    `[secrets-loader] Loaded secret "${secretName}" from AWS Secrets Manager ` +
    `(${injectedCount} vars injected into process.env, ` +
    `${Object.keys(secrets).length - injectedCount} already present/skipped)`
  );

  _loaded = true;
  _secretCache = secrets;
  return secrets;
}

/**
 * Top-level initializer called by each service's entry point.
 *
 * Usage:
 *   const { initSecrets } = require('./secrets-loader');
 *   await initSecrets('thinkvelocity/production/consumer-backend');
 *
 * @param {string} serviceName - Full AWS Secrets Manager secret name for this service
 * @returns {Promise<void>}
 */
async function initSecrets(serviceName) {
  if (!serviceName || typeof serviceName !== 'string') {
    throw new Error('[secrets-loader] initSecrets() requires a non-empty serviceName string');
  }
  await loadSecrets(serviceName);
}

module.exports = { initSecrets, loadSecrets };
