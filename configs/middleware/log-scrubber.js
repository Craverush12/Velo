/**
 * ThinkVelocity — Log Scrubber Middleware (Express / Node.js)
 * SOC2 CC6.7 — No sensitive data in logs
 *
 * Usage:
 *   const { scrubLogs, scrubString } = require('./configs/middleware/log-scrubber');
 *   app.use(scrubLogs());
 *
 * In production, console.error and console.warn are automatically overridden
 * to pass all arguments through scrubString before printing.
 */

'use strict';

// ---------------------------------------------------------------------------
// Compiled Regexes — defined once at module load, never per-call
// ---------------------------------------------------------------------------

/** JWT bearer tokens (header.payload.signature) */
const RE_JWT = /eyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+/g;

/** Groq API keys */
const RE_GROQ = /gsk_[A-Za-z0-9]{20,}/g;

/** OpenAI / generic sk- keys */
const RE_OPENAI = /sk-[A-Za-z0-9]{20,}/g;

/** SendGrid API keys */
const RE_SENDGRID = /SG\.[A-Za-z0-9\-_]{22,}\.[A-Za-z0-9\-_]{43,}/g;

/** Razorpay key IDs and secrets (rzp_live_ / rzp_test_) */
const RE_RAZORPAY_KEY = /rzp_(live|test)_[A-Za-z0-9]{14,}/g;

/** Razorpay payment signatures (40-char hex) in context strings */
const RE_RAZORPAY_SIG = /(razorpay_signature|payment_signature)[=:\s"']+[a-f0-9]{40}/gi;

/** AWS access key IDs */
const RE_AWS_KEY = /AKIA[A-Z0-9]{16}/g;

/** AWS secret access keys (40-char base64-ish after common field names) */
const RE_AWS_SECRET = /(aws_secret_access_key|aws_secret)[=:\s"']+[A-Za-z0-9\/+]{40}/gi;

/** 6-digit OTP codes that appear in auth-context strings */
const RE_OTP = /\b(otp|one.?time.?pass(word)?|verification.?code)[=:\s"']+\d{6}\b/gi;

/** UUID refresh tokens (UUID v4 pattern) */
const RE_UUID_TOKEN = /(refresh_token|refresh|token_id)[=:\s"']+[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}/gi;

/** Credit card PAN (Luhn-range: 13–19 digits, optionally space/dash separated) */
const RE_PAN = /\b(?:\d[ \-]?){13,18}\d\b/g;

/** Email addresses — partially masked */
const RE_EMAIL = /\b([A-Za-z0-9._%+\-]+)@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})\b/g;

// Fields whose VALUES should always be redacted regardless of content
const SENSITIVE_FIELD_RE = /^(password|passwd|pwd|secret|token|api[_\-]?key|auth|credential|authorization|private[_\-]?key|access[_\-]?key|refresh[_\-]?token|otp|pin|card[_\-]?number|cvv|ssn|passphrase)$/i;

// ---------------------------------------------------------------------------
// scrubString — scrub an arbitrary string before logging
// ---------------------------------------------------------------------------

/**
 * Scrub a string of all known sensitive patterns.
 * @param {string} str
 * @returns {string}
 */
function scrubString(str) {
  if (typeof str !== 'string') {
    return str;
  }

  return str
    // JWTs first (they start with eyJ and look like base64)
    .replace(RE_JWT, '[JWT_REDACTED]')
    // API keys
    .replace(RE_GROQ, '[GROQ_KEY_REDACTED]')
    .replace(RE_OPENAI, '[OPENAI_KEY_REDACTED]')
    .replace(RE_SENDGRID, '[SENDGRID_KEY_REDACTED]')
    // Razorpay
    .replace(RE_RAZORPAY_KEY, '[RAZORPAY_KEY_REDACTED]')
    .replace(RE_RAZORPAY_SIG, '$1=[RAZORPAY_SIG_REDACTED]')
    // AWS
    .replace(RE_AWS_KEY, '[AWS_KEY_ID_REDACTED]')
    .replace(RE_AWS_SECRET, '$1=[AWS_SECRET_REDACTED]')
    // Auth context
    .replace(RE_OTP, '$1=[OTP_REDACTED]')
    .replace(RE_UUID_TOKEN, '$1=[REFRESH_TOKEN_REDACTED]')
    // PAN (credit card) — replace all digit groups but keep length hint
    .replace(RE_PAN, '[PAN_REDACTED]')
    // Email — mask domain
    .replace(RE_EMAIL, (_, user, domain) => `${user[0]}***@***.${domain.split('.').pop()}`);
}

// ---------------------------------------------------------------------------
// scrubObject — deep-scrub a plain object (request body, query params, etc.)
// ---------------------------------------------------------------------------

/**
 * Recursively scrub an object's values.
 * Keys matching SENSITIVE_FIELD_RE have their entire value replaced.
 * String values have known patterns scrubbed.
 * @param {*} obj
 * @param {number} [depth=0]
 * @returns {*}
 */
function scrubObject(obj, depth = 0) {
  if (depth > 10) return '[DEPTH_LIMIT]'; // prevent circular reference blowup

  if (obj === null || obj === undefined) return obj;

  if (typeof obj === 'string') return scrubString(obj);

  if (Array.isArray(obj)) {
    return obj.map((item) => scrubObject(item, depth + 1));
  }

  if (typeof obj === 'object') {
    const out = {};
    for (const [key, value] of Object.entries(obj)) {
      if (SENSITIVE_FIELD_RE.test(key)) {
        out[key] = '[REDACTED]';
      } else {
        out[key] = scrubObject(value, depth + 1);
      }
    }
    return out;
  }

  return obj;
}

// ---------------------------------------------------------------------------
// Console override — installed in production to scrub all error/warn output
// ---------------------------------------------------------------------------

let _consoleOverrideInstalled = false;

function installConsoleOverride() {
  if (_consoleOverrideInstalled) return;
  _consoleOverrideInstalled = true;

  const _originalError = console.error.bind(console);
  const _originalWarn = console.warn.bind(console);

  console.error = (...args) => {
    const scrubbed = args.map((a) =>
      typeof a === 'string' ? scrubString(a) : a
    );
    _originalError(...scrubbed);
  };

  console.warn = (...args) => {
    const scrubbed = args.map((a) =>
      typeof a === 'string' ? scrubString(a) : a
    );
    _originalWarn(...scrubbed);
  };
}

// ---------------------------------------------------------------------------
// Express middleware
// ---------------------------------------------------------------------------

/**
 * Returns an Express middleware that:
 *  1. Installs console.error / console.warn scrubbers in production.
 *  2. Logs each request/response as a single-line JSON with safe fields only.
 *  3. Does NOT log request body content (may contain PII).
 *
 * @param {object} [options]
 * @param {boolean} [options.overrideConsole=true]  Install console override in prod.
 * @param {string}  [options.logLevel='info']        Minimum level to emit request logs.
 * @returns {function} Express middleware
 */
function scrubLogs(options = {}) {
  const { overrideConsole = true } = options;

  // Override console in production
  if (overrideConsole && process.env.NODE_ENV === 'production') {
    installConsoleOverride();
  }

  return function logScrubberMiddleware(req, res, next) {
    const startMs = Date.now();

    // Scrub body in-place for any downstream middleware that might log req.body.
    // We overwrite req.body with a scrubbed clone so no sensitive field values
    // can leak via accidental body logging by other middleware.
    if (req.body && typeof req.body === 'object') {
      req.body = scrubObject(req.body);
    }

    // Capture finish event to log response
    res.on('finish', () => {
      const durationMs = Date.now() - startMs;

      const logEntry = {
        timestamp: new Date().toISOString(),
        level: res.statusCode >= 500 ? 'error' : res.statusCode >= 400 ? 'warn' : 'info',
        method: req.method,
        path: scrubString(req.path),          // scrub any accidental secret in path
        status: res.statusCode,
        duration_ms: durationMs,
        user_agent: req.headers['user-agent'] || '',
        request_id: req.headers['x-request-id'] || req.headers['x-correlation-id'] || '',
        // Never log: req.body, req.headers.authorization, query string values
      };

      // Emit as single-line JSON to stdout (structured logging)
      process.stdout.write(JSON.stringify(logEntry) + '\n');
    });

    next();
  };
}

// ---------------------------------------------------------------------------
// Exports
// ---------------------------------------------------------------------------

module.exports = {
  scrubLogs,
  scrubString,
  scrubObject,
};
