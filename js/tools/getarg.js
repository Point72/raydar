export const getarg = (flag, ...args) => {
    if (Array.isArray(flag)) {
      flag = flag.map((x, i) => x + (args[i] || "")).join("");
    }
    const argv = process.argv.slice(2);
    if (flag) {
      const index = argv.indexOf(flag);
      if (index > -1) {
        const next = argv[index + 1];
        if (next) {
          return next;
        } else {
          return true;
        }
      }
    } else {
      return argv
        .map(function (arg) {
          return "'" + arg.replace(/'/g, "'\\''") + "'";
        })
        .join(" ");
    }
  };
