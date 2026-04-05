import { build } from "@finos/perspective-esbuild-plugin/build.js";
<<<<<<< before updating
import { BuildCss } from "@prospective.co/procss/target/cjs/procss.js";
import cpy from "cpy";
import fs from "fs";
import { createRequire } from "node:module";
=======
import { transform } from "lightningcss";
import { getarg } from "./tools/getarg.mjs";
import fs from "fs";
import cpy from "cpy";

const DEBUG = getarg("--debug");

const COMMON_DEFINE = {
  global: "window",
  "process.env.DEBUG": `${DEBUG}`,
};
>>>>>>> after updating

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

<<<<<<< before updating
const require = createRequire(import.meta.url);
function add(builder, path, path2) {
  builder.add(path, fs.readFileSync(require.resolve(path2 || path)).toString());
=======
async function compile_css() {
  const process_path = (path) => {
    const outpath = path.replace("src/css", "dist/css");
    fs.mkdirSync(outpath, { recursive: true });

    fs.readdirSync(path, { withFileTypes: true }).forEach((entry) => {
      const input = `${path}/${entry.name}`;
      const output = `${outpath}/${entry.name}`;

      if (entry.isDirectory()) {
        process_path(input);
      } else if (entry.isFile() && entry.name.endsWith(".css")) {
        const source = fs.readFileSync(input);
        const { code } = transform({
          filename: entry.name,
          code: source,
          minify: !DEBUG,
          sourceMap: false,
        });
        fs.writeFileSync(output, code);
      }
    });
  };

  process_path("src/css");
>>>>>>> after updating
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
