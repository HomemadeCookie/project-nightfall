// Copy the pipeline's baked output (repo-root dist/) into public/ so dev and build serve real data.
// Run `nightfall publish` first. If no data exists we write a tiny placeholder so the app still loads.
import { cpSync, existsSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const src = resolve(process.env.NIGHTFALL_DIST ?? resolve(here, "../../../dist"));
const pub = resolve(here, "../public");

for (const name of ["answers", "data", "eval"]) rmSync(resolve(pub, name), { recursive: true, force: true });
if (existsSync(resolve(src, "manifest.json"))) {
  for (const name of ["manifest.json", "blocked.json"]) {
    if (existsSync(resolve(src, name))) cpSync(resolve(src, name), resolve(pub, name));
  }
  for (const name of ["answers", "data", "eval"]) {
    if (existsSync(resolve(src, name))) cpSync(resolve(src, name), resolve(pub, name), { recursive: true });
  }
  console.log(`synced data from ${src}`);
} else {
  mkdirSync(pub, { recursive: true });
  writeFileSync(resolve(pub, "manifest.json"), JSON.stringify({ empty: true }));
  console.warn(`no data at ${src}; run \`nightfall publish\` in pipeline/ first`);
}
