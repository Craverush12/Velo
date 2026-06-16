/**
 * enterprise-backend-startup.ts — Bootstrap patch for the NestJS enterprise backend
 *
 * SECRET NAME: thinkvelocity/production/enterprise-backend
 * SERVICE PORT: 3000
 *
 * PURPOSE
 * -------
 * NestJS resolves configuration at module instantiation time (decorators,
 * ConfigService, TypeORM DataSource, etc.).  Secrets MUST be in process.env
 * before NestFactory.create() is called.  This file replaces main.ts as the
 * true entry point, loading secrets first and then delegating to NestJS bootstrap.
 *
 * HOW TO INTEGRATE
 * ----------------
 * 1. Copy secrets-loader.js into your project (e.g. src/secrets-loader.js).
 *    The loader is plain CommonJS and works fine when required from TypeScript
 *    via ts-node or from compiled JS in production.
 *
 * 2. Rename your current main.ts to main.core.ts (or keep it and just prepend
 *    the initSecrets call — see Option B below).
 *
 * 3. Create THIS file as src/main.ts (replacing the original).
 *
 * 4. Update your Dockerfile CMD and nest-cli.json entryFile if needed:
 *
 *      # nest-cli.json  (if you use "entryFile" key)
 *      { "entryFile": "main" }
 *
 *      # Dockerfile (compiled dist — adjust path as needed)
 *      CMD ["node", "dist/main.js"]
 *
 * LOCAL DEV BEHAVIOUR
 * -------------------
 * dotenv is called first.  If .env is present, it populates process.env.
 * If AWS_REGION is then absent (typical for local dev), secrets-loader skips
 * Secrets Manager entirely.  The service boots purely from .env values.
 *
 * OPTION B — Inline patch (no file rename needed)
 * ------------------------------------------------
 * If you prefer not to rename main.ts, prepend these lines to your existing
 * main.ts, ABOVE the @nestjs/core import:
 *
 *   import * as dotenv from 'dotenv';
 *   dotenv.config();
 *   // eslint-disable-next-line @typescript-eslint/no-var-requires
 *   const { initSecrets } = require('./secrets-loader');
 *   // Wrap bootstrap() body in: await initSecrets(...); first
 */

// ---------------------------------------------------------------------------
// Step 1 — Load .env for local dev (no-op if file is absent)
// ---------------------------------------------------------------------------
import * as dotenv from 'dotenv';
dotenv.config();

// ---------------------------------------------------------------------------
// Step 2 — Pull secrets from AWS Secrets Manager before NestJS boots
// ---------------------------------------------------------------------------
// secrets-loader.js is plain CommonJS — require() works fine here.
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { initSecrets } = require('./secrets-loader');

const SECRET_NAME = 'thinkvelocity/production/enterprise-backend';

// ---------------------------------------------------------------------------
// Step 3 — Import NestJS AFTER the secrets call (dynamic import inside async)
//           so that module-level decorators read the final process.env values.
// ---------------------------------------------------------------------------
async function bootstrap(): Promise<void> {
  // Populate process.env from Secrets Manager (or skip gracefully if local dev)
  await initSecrets(SECRET_NAME);

  // Dynamic import ensures NestJS module decorators execute AFTER process.env
  // has been fully populated.  If your tsconfig has "module": "commonjs" this
  // compiles to a regular require() call which is also fine.
  const { NestFactory } = await import('@nestjs/core');

  // Replace AppModule with the path to your actual root module if it differs.
  const { AppModule } = await import('./app.module');

  const app = await NestFactory.create(AppModule, {
    logger: ['log', 'warn', 'error'],
  });

  // ── Optional: global prefix, CORS, pipes ──────────────────────────────────
  // Uncomment and adjust to match your existing main.ts configuration:
  //
  // app.setGlobalPrefix('backend');
  //
  // app.enableCors({
  //   origin: process.env.ALLOWED_ORIGINS?.split(',') ?? [],
  //   credentials: true,
  // });
  //
  // app.useGlobalPipes(new ValidationPipe({ whitelist: true, transform: true }));
  // ─────────────────────────────────────────────────────────────────────────

  const port = process.env.PORT ?? 3000;
  await app.listen(port);
  console.log(`[enterprise-backend] Listening on port ${port}`);
}

bootstrap().catch((err: unknown) => {
  console.error('[enterprise-backend] Fatal error during startup:', err);
  process.exit(1);
});
