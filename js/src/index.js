import perspective from "@finos/perspective";
import "@finos/perspective-viewer";
import "@finos/perspective-viewer-datagrid";
import "@finos/perspective-viewer-d3fc";
import "@finos/perspective-workspace/dist/css/pro.css";
import "@finos/perspective-viewer/dist/css/themes.css";
import "@finos/perspective-workspace";
import "./index.css";

function removeTrailingSlash(url) {
  return url.replace(/\/$/, "");
}

async function load() {
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
      registeredTables.add(tableName);
      workspace.addTable(tableName, await websocket.open_table(tableName));
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
  workspace.restore(layoutData);

  await updateTables();

  // update tables every 5s
  setInterval(updateTables, 5000);
}

load();
