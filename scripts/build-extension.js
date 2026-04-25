#!/usr/bin/env node
/**
 * Onichan Bypasser — Secure Extension Builder
 * Obfuscates popup.js, background.js, content.js, stripe-overlay.js
 * Minifies popup.css + stripe-overlay.css
 * Packages final ZIP
 */

import { readFileSync, writeFileSync, mkdirSync, cpSync, rmSync, existsSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import { execSync } from "child_process";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT    = resolve(__dirname, "..");
const SRC     = resolve(ROOT, "src/onichan-extension");
const BUILD   = resolve(ROOT, "src/onichan-extension-dist");
const OUT_ZIP = resolve(ROOT, "onichan-bypasser-extension.zip");

// JS files to obfuscate (jeffrey-inject.js is already obfuscated — skip it)
const MY_JS = [
  "popup.js",
  "background.js",
  "content.js",
  "stripe-overlay.js",
];

// CSS files to minify
const MY_CSS = [
  "popup.css",
  "stripe-overlay.css",
];

// ── 1. Clean build dir ──────────────────────────────────────────────────────
if (existsSync(BUILD)) rmSync(BUILD, { recursive: true });
mkdirSync(BUILD, { recursive: true });
cpSync(SRC, BUILD, { recursive: true });
console.log("✅ Copied source → dist");

// ── 2. Load obfuscator ──────────────────────────────────────────────────────
const { default: JsObfuscator } = await import("javascript-obfuscator");

const STRONG = {
  compact:                            true,
  controlFlowFlattening:              true,
  controlFlowFlatteningThreshold:     0.75,
  deadCodeInjection:                  true,
  deadCodeInjectionThreshold:         0.4,
  identifierNamesGenerator:           "hexadecimal",
  numbersToExpressions:               true,
  renameGlobals:                      false,
  selfDefending:                      false,
  simplify:                           true,
  splitStrings:                       true,
  splitStringsChunkLength:            7,
  stringArray:                        true,
  stringArrayCallsTransform:          true,
  stringArrayCallsTransformThreshold: 0.75,
  stringArrayEncoding:                ["base64"],
  stringArrayIndexShift:              true,
  stringArrayRotate:                  true,
  stringArrayShuffle:                 true,
  stringArrayWrappersCount:           3,
  stringArrayWrappersChunkLength:     3,
  stringArrayWrappersParametersMaxCount: 5,
  stringArrayWrappersType:            "function",
  stringArrayThreshold:               0.8,
  transformObjectKeys:                true,
  unicodeEscapeSequence:              false,
};

// ── 3. Obfuscate JS files ───────────────────────────────────────────────────
for (const rel of MY_JS) {
  const path = resolve(BUILD, rel);
  if (!existsSync(path)) { console.warn(`⚠️  Skipped (not found): ${rel}`); continue; }
  const src  = readFileSync(path, "utf-8");
  const obf  = JsObfuscator.obfuscate(src, STRONG).getObfuscatedCode();
  writeFileSync(path, obf, "utf-8");
  const [b, a] = [(Buffer.byteLength(src)/1024).toFixed(1), (Buffer.byteLength(obf)/1024).toFixed(1)];
  console.log(`✅ Obfuscated  ${rel}  (${b} KB → ${a} KB)`);
}

// ── 4. Minify CSS ───────────────────────────────────────────────────────────
for (const rel of MY_CSS) {
  const path = resolve(BUILD, rel);
  if (!existsSync(path)) continue;
  let css = readFileSync(path, "utf-8");
  css = css
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\s{2,}/g, " ")
    .replace(/\s*([:;{},(>~+])\s*/g, "$1")
    .replace(/;\}/g, "}")
    .trim();
  writeFileSync(path, css, "utf-8");
  console.log(`✅ Minified    ${rel}`);
}

// ── 5. Package ZIP via Python ───────────────────────────────────────────────
const pyScript = resolve(ROOT, "src", "_pack_ext.py");
writeFileSync(pyScript, `import zipfile, pathlib
build = pathlib.Path(r"${BUILD.replace(/\\/g, "/")}")
out   = pathlib.Path(r"${OUT_ZIP.replace(/\\/g, "/")}")
out.unlink(missing_ok=True)
with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for f in sorted(build.rglob("*")):
        if f.is_file() and ".git" not in f.parts and "__pycache__" not in f.parts:
            zf.write(f, f.relative_to(build))
sz = out.stat().st_size / (1024*1024)
count = len(zipfile.ZipFile(out).namelist())
print(f"{sz:.2f} MB  {count} files")
`);
const result = execSync(`python3 "${pyScript}"`, { encoding: "utf-8" }).trim();
import { unlinkSync } from "fs";
try { unlinkSync(pyScript); } catch {}
console.log(`\n🎀  onichan-bypasser-extension.zip — ${result}`);
console.log("   Load unpacked → select dist folder");
console.log(`   Dist: ${BUILD}`);
