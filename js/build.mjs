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
  });
}

build_all();
