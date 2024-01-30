import { PerspectiveEsbuildPlugin } from "@finos/perspective-esbuild-plugin";
import { build } from "esbuild";
import { BuildCss } from "@prospective.co/procss/target/cjs/procss.js";
import fs from "fs";
import { copyFile } from "fs/promises";

async function compile_css() {
  const builder = new BuildCss("");
  builder.add("index.css", fs.readFileSync("./src/index.css").toString());
  fs.writeFileSync("dist/index.css", builder.compile().get("index.css"));
}

async function build_all() {
  await copyFile("./src/index.html", "dist/index.html");
  await copyFile("./src/layouts/default.json", "dist/layouts/default.json");
  await compile_css();
  await build({
    entryPoints: ["src/index.js"],
    outfile: "dist/index.js",
    plugins: [PerspectiveEsbuildPlugin()],
    format: "esm",
    bundle: true,
    minify: true,
    loader: {
      ".ttf": "file",
    },
  });
}

build_all();
