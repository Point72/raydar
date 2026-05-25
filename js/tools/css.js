import { bundleAsync } from "lightningcss";
import { getarg } from "./getarg.js";
import fs from "fs";
import path from "path";

const DEBUG = getarg("--debug");

const DEFAULT_RESOLVER = {
  resolve(specifier, originatingFile) {
    if (/^https?:\/\//.test(specifier)) {
      return specifier;
    }

    if (specifier.startsWith("perspective-viewer-")) {
      const viewerCssDir = path.resolve(
        "node_modules/@perspective-dev/viewer/dist/css",
      );
      const normalized = specifier.replace(/^perspective-viewer-/, "");
      const normalizedPath = path.join(viewerCssDir, normalized);
      if (fs.existsSync(normalizedPath)) {
        return normalizedPath;
      }
      return path.join(viewerCssDir, specifier);
    }
    return path.resolve(path.dirname(originatingFile), specifier);
  },
};

export const compile = async (root = "src/index.css", resolver = null) => {
  const { code } = await bundleAsync({
    filename: path.resolve(root),
    minify: !DEBUG,
    sourceMap: false,
    resolver: resolver || DEFAULT_RESOLVER,
  });
  fs.mkdirSync("./dist", { recursive: true });
  fs.writeFileSync("./dist/index.css", code);
}
