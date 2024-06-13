import perspective from "@finos/perspective";
import "@finos/perspective-viewer";
import "@finos/perspective-viewer-datagrid";
import "@finos/perspective-viewer-d3fc";
import "@finos/perspective-workspace/dist/css/pro.css";
import "@finos/perspective-viewer/dist/css/themes.css";
import "@finos/perspective-workspace";
import "./index.css";

window.addEventListener("load", async () => {
  const workspace = document.querySelector("perspective-workspace");
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const websocket = perspective.websocket(
    `${protocol}//${window.location.host}${window.location.pathname}/ws`,
  );
  const registeredTables = new Set();
  const worker = perspective.worker();

  const updateTables = async () => {
    const response = await fetch(`${window.location.href}/tables`);
    const tables = await response.json();

    tables.map(async (tableName) => {
      if (registeredTables.has(tableName)) return;
      registeredTables.add(tableName);
      fetch("static/layouts/default.json")
        .then((response) => response.json())
        .then((data) => {
          console.log("Loading layout from static/layouts/default.json...");
          workspace.restore(data);
        })
        .catch((error) => {
          console.error("ERROR:", error);
        });
      workspace.addTable(tableName, websocket.open_table(tableName));
    });
  };

  await updateTables();

  // update tables every 5s
  setInterval(updateTables, 5000);
});
