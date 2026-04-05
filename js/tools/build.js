import esbuild from "esbuild";

const CUTOFF_PERCENT = 0.02;

const DEFAULT_BUILD = {
    target: ["es2022"],
    bundle: true,
    minify: !process.env.PSP_DEBUG,
    sourcemap: true,
    metafile: true,
    entryNames: "[name]",
    chunkNames: "[name]",
    assetNames: "[name]",
};

export const build = async (config) => {
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
