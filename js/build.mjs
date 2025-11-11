import { build } from "@finos/perspective-esbuild-plugin/build.js";
import { BuildCss } from "@prospective.co/procss/target/cjs/procss.js";
import cpy from "cpy";
import fs from "fs";
import { createRequire } from "node:module";

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

const require = createRequire(import.meta.url);
function add(builder, path, path2) {
  builder.add(path, fs.readFileSync(require.resolve(path2 || path)).toString());
}

async function compile_css() {
  const builder1 = new BuildCss("");
  add(builder1, "./src/index.css");
  add(
    builder1,
    "perspective-viewer-pro.css",
    "@perspective-dev/viewer/dist/css/pro.css",
  );
  add(
    builder1,
    "perspective-viewer-pro-dark.css",
    "@perspective-dev/viewer/dist/css/pro-dark.css",
  );
  add(
    builder1,
    "perspective-viewer-monokai.css",
    "@perspective-dev/viewer/dist/css/monokai.css",
  );
  add(
    builder1,
    "perspective-viewer-vaporwave.css",
    "@perspective-dev/viewer/dist/css/vaporwave.css",
  );
  add(
    builder1,
    "perspective-viewer-dracula.css",
    "@perspective-dev/viewer/dist/css/dracula.css",
  );
  add(
    builder1,
    "perspective-viewer-gruvbox.css",
    "@perspective-dev/viewer/dist/css/gruvbox.css",
  );
  add(
    builder1,
    "perspective-viewer-gruvbox-dark.css",
    "@perspective-dev/viewer/dist/css/gruvbox-dark.css",
  );
  add(
    builder1,
    "perspective-viewer-solarized.css",
    "@perspective-dev/viewer/dist/css/solarized.css",
  );
  add(
    builder1,
    "perspective-viewer-solarized-dark.css",
    "@perspective-dev/viewer/dist/css/solarized-dark.css",
  );

  const css = builder1.compile().get("index.css");

  // write to extension
  fs.writeFileSync("./dist/index.css", css);
}

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
  await compile_css();

  /* Copy to raydar static */
  await cpy("./dist/*", "../raydar/dashboard/static/", {
    flat: true,
    recursive: true,
  });
  await cpy("./dist/layouts/*", "../raydar/dashboard/static/layouts/", {
    flat: true,
    recursive: true,
  });
}

build_all();
