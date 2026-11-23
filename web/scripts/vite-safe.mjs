// Preserve the Vite configuration while explicitly disabling dotenv discovery.
import { build, createServer, preview } from 'vite';
const mode = process.argv[2];
const config = { envFile: false };
if (mode === 'build') await build(config);
else if (mode === 'dev') {
  const server = await createServer(config);
  await server.listen();
  server.printUrls();
} else if (mode === 'preview') {
  const server = await preview(config);
  server.printUrls();
} else throw new Error('Expected dev, build or preview');
