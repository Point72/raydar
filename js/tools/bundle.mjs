import { getarg } from "./getarg.mjs";
import esbuild from "esbuild";

const DEBUG = getarg("--debug");

const CUTOFF_PERCENT = 0.02;

const COMMON_DEFINE = {
  global: "window",
  "process.env.DEBUG": `${DEBUG}`,
};

const COMMON_LOADER = {
    ".css": "text",
    ".html": "text",
    ".jsx": "jsx",
    ".png": "file",
    ".ttf": "file",
    ".wasm": "file",
};

const DEFAULT_BUILD = {
    target: ["es2022"],
    bundle: true,
    format: "esm",
    minify: DEBUG,
    sourcemap: true,
    metafile: true,
    entryNames: "[name]",
    chunkNames: "[name]",
    assetNames: "[name]",
    define: COMMON_DEFINE,
    loader: COMMON_LOADER,
    plugins: [],
};

export const bundle = async (config) => {
    const result = await esbuild.build({
        ...DEFAULT_BUILD,
        ...config,
    });

    if (result.metafile) {
        for (const output of Object.keys(result.metafile.outputs)) {
            const { inputs, bytes } = result.metafile.outputs[output];
            for (const input of Object.keys(inputs)) {
                if (inputs[input].bytesInOutput / bytes < CUTOFF_PERCENT) {
                    delete inputs[input];
                }
            }
        }

        const text = await esbuild.analyzeMetafile(result.metafile, {
            color: true,
        });

        console.log(text);
    }
};
