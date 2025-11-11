import perspective from "@perspective-dev/client";
import perspective_viewer from "@perspective-dev/viewer";
import SERVER_WASM from "@perspective-dev/server/dist/wasm/perspective-server.wasm";
import CLIENT_WASM from "@perspective-dev/viewer/dist/wasm/perspective-viewer.wasm";

import "@perspective-dev/workspace";
import "@perspective-dev/viewer-datagrid";
import "@perspective-dev/viewer-d3fc";

const perspective_init_promise = Promise.all([
  perspective.init_server(fetch(SERVER_WASM)),
  perspective_viewer.init_client(fetch(CLIENT_WASM)),
]);

function removeTrailingSlash(url) {
  return url.replace(/\/$/, "");
}

async function load() {
  await perspective_init_promise;
  const workspace = document.querySelector("perspective-workspace");
  const saveButton = document.getElementById("save-layout-button");
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const websocket = await perspective.websocket(
    `${protocol}//${window.location.host}${removeTrailingSlash(
      window.location.pathname,
    )}/ws`,
  );
  const registeredTables = new Set();

  const updateTables = async () => {
    const response = await fetch(
      `${removeTrailingSlash(window.location.href)}/tables`,
    );
    const tables = await response.json();

    tables.map(async (tableName) => {
      if (registeredTables.has(tableName)) return;
      console.log(`Registering table: ${tableName}`);
      registeredTables.add(tableName);
      await workspace.addTable(
        tableName,
        await websocket.open_table(tableName),
      );
    });
  };

  document.body.addEventListener("dragover", (e) => {
    e.preventDefault();
  });

  document.body.addEventListener("drop", (e) => {
    e.preventDefault();

    const file = e.dataTransfer.files[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (event) => {
        try {
          const json = JSON.parse(event.target.result);
          workspace.restore(json);
          console.log("File contents:", json);
        } catch (error) {
          console.error("Error parsing JSON:", error);
        }
      };
      reader.readAsText(file);
    }
  });

  saveButton.addEventListener("click", function () {
    let workspace = document.querySelector("perspective-workspace");

    workspace.save().then((config) => {
      // Convert the configuration object to a JSON string
      let json = JSON.stringify(config);

      // Create a Blob object from the JSON string
      let blob = new Blob([json], { type: "application/json" });

      // Create a download link
      let link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = "workspace.json";

      // Append the link to the document body and click it to start the download
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    });
  });

  const layouts = await fetch("static/layouts/default.json");
  const layoutData = await layouts.json();
  console.log("Loading layout from static/layouts/default.json...");

  if (Object.keys(layoutData).length > 0) {
    await workspace.restore(layoutData);
  }

  await updateTables();

  // update tables every 5s
  setInterval(updateTables, 5000);
}

load();
