import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const [, , inputPath, nodeModules] = process.argv;
if (!inputPath || !nodeModules) {
  process.stderr.write('usage: validate-gltf.mjs <input.glb> <node_modules>\n');
  process.exit(2);
}

const requireFromInstall = createRequire(path.join(nodeModules, 'gltf-validator', 'package.json'));
const validator = requireFromInstall('gltf-validator');
const bytes = new Uint8Array(fs.readFileSync(inputPath));
const report = await validator.validateBytes(bytes, {
  uri: path.basename(inputPath),
  externalResourceFunction: async (uri) => {
    const target = path.resolve(path.dirname(inputPath), uri);
    const parent = path.resolve(path.dirname(inputPath));
    if (target !== parent && !target.startsWith(parent + path.sep)) {
      throw new Error(`external resource escapes input directory: ${uri}`);
    }
    return new Uint8Array(fs.readFileSync(target));
  },
});
process.stdout.write(JSON.stringify(report));
