// Build the browser preview inside the isolated runner.
import fs from 'node:fs/promises';
import path from 'node:path';

async function preview() {
  const { build } = await import('vite');
  const { default: vue } = await import('@vitejs/plugin-vue');
  const output = await build({
    root: process.cwd(), configFile: false, envFile: false, publicDir: false,
    base: './', plugins: [vue()], logLevel: 'silent',
    build: { write: false, assetsInlineLimit: 1024 * 1024, rollupOptions: { output: { inlineDynamicImports: true } } },
  });
  const dir = process.argv[2];
  let size = 0;
  for (const entry of output.output) {
    const target = path.resolve(dir, entry.fileName);
    if (!target.startsWith(dir + path.sep)) throw new Error('预览资源路径无效');
    const content = entry.type === 'chunk' ? entry.code : entry.source;
    size += Buffer.byteLength(content);
    if (size > 4 * 1024 * 1024) throw new Error('预览产物超过 4 MiB');
    await fs.mkdir(path.dirname(target), { recursive: true });
    await fs.writeFile(target, content);
  }
}

await preview();
