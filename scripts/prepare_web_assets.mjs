import { mkdir, copyFile } from 'node:fs/promises';
import path from 'node:path';
const root = path.resolve(import.meta.dirname, '..');
const destination = path.join(root, 'web', 'public', 'api-doc-assets');
await mkdir(destination, { recursive: true });
for (const filename of ['swagger-ui-bundle.js', 'swagger-ui.css']) {
  await copyFile(
    path.join(root, 'web', 'node_modules', 'swagger-ui-dist', filename),
    path.join(destination, filename),
  );
}
