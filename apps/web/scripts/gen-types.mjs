// Generate src/data/contracts.ts from the JSON Schemas the pipeline writes (`nightfall contracts`).
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { compile } from "json-schema-to-typescript";

const here = dirname(fileURLToPath(import.meta.url));
const schema = JSON.parse(readFileSync(resolve(here, "../../../contracts/answer.schema.json"), "utf8"));
const ts = await compile(schema, "Answer", {
  bannerComment: "/* Generated from contracts/answer.schema.json. Do not edit. */",
  additionalProperties: false,
});
writeFileSync(resolve(here, "../src/data/contracts.ts"), ts);
console.log("wrote src/data/contracts.ts");
