<<<<<<< before updating
import { build } from "./tools/build.js";
import { compile } from "./tools/css.js";
import fs from "fs";
import cpy from "cpy";

const BUILD = [
  {
    define: {
      global: "window",
    },
    entryPoints: ["src/index.js"],
    bundle: true,
    plugins: [],
    format: "esm",
    loader: {
      ".css": "text",
      ".html": "text",
      ".jsx": "jsx",
      ".png": "file",
      ".ttf": "file",
      ".wasm": "file",
    },
    outfile: "./dist/index.js",
    publicPath: "/static/",
  },
];

async function build_all() {
  /* make directories */
  fs.mkdirSync("../raydar/dashboard/static/", { recursive: true });

  /* Compile JS */
  await Promise.all(BUILD.map(build)).catch(() => process.exit(1));
  // await cp_to_paths("./src/style/*.css");
  await cpy("./src/*.html", "./dist", { flat: true });
  await cpy("./src/layouts/*", "./dist/layouts", { flat: true });
  await cpy(
    "./node_modules/@perspective-dev/server/dist/wasm/perspective-server.wasm",
    "./dist",
    { flat: true },
  );
  await cpy(
    "./node_modules/@perspective-dev/viewer/dist/wasm/perspective-viewer.wasm",
    "./dist",
    { flat: true },
  );

  /* Compile css */
  await compile();

  /* Copy to raydar static */
  await cpy("./dist/*", "../raydar/dashboard/static/", {
    flat: true,
    recursive: true,
  });
  await cpy("./dist/layouts/*", "../raydar/dashboard/static/layouts/", {
    flat: true,
    recursive: true,
=======
import { bundle } from "./tools/bundle.mjs";
import { bundle_css } from "./tools/css.mjs";
import { node_modules_external } from "./tools/externals.mjs";

import fs from "fs";
import cpy from "cpy";

const BUNDLES = [
  {
    entryPoints: ["src/ts/index.ts"],
    plugins: [node_modules_external()],
    outfile: "dist/esm/index.js",
  },
  {
    entryPoints: ["src/ts/index.ts"],
    outfile: "dist/cdn/index.js",
  },
];

async function build() {
  // Bundle css
  await bundle_css();

  // Copy HTML
  cpy("src/html/*", "dist/");

  // Copy images
  fs.mkdirSync("dist/img", { recursive: true });
  cpy("src/img/*", "dist/img");

  await Promise.all(BUNDLES.map(bundle)).catch(() => process.exit(1));

  // Copy servable assets to python extension (exclude esm/)
  fs.mkdirSync("../raydar/extension", { recursive: true });
  cpy("dist/**/*", "../raydar/extension", {
    filter: (file) => !file.relativePath.startsWith("esm"),
>>>>>>> after updating
  });
}

build();
