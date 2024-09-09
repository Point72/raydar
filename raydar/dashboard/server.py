from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from os import environ
from os.path import abspath, dirname, join
from perspective import PerspectiveManager, PerspectiveStarletteHandler, Table
from pydantic import BaseModel, Field
from ray.serve import Application, deployment, ingress
from threading import Thread
from traceback import format_exc


class PerspectiveRayServerArgs(BaseModel):
    name: str = Field(default="Perspective")
    manager: str = Field(default_factory=PerspectiveManager)


def perspective_thread(manager: PerspectiveManager):
    from asyncio import new_event_loop

    psp_loop = new_event_loop()
    manager.set_loop_callback(psp_loop.call_soon_threadsafe)
    psp_loop.run_forever()


app = FastAPI()

static_files_dir = join(abspath(dirname(__file__)), "static")
app.mount("/static", StaticFiles(directory=static_files_dir, check_dir=False, html=True))


@deployment(name="Perspective_Web_Server", num_replicas=1)
@ingress(app)
class PerspectiveRayServer:
    def __init__(self, args: PerspectiveRayServerArgs = None):
        args = args or PerspectiveRayServerArgs()
        self._manager = args.manager
        self._schemas = {}
        self._tables = {}
        self._psp_thread = Thread(target=perspective_thread, args=(self._manager,), daemon=True)
        self._psp_thread.start()

    def new_table(self, tablename: str, schema) -> None:
        if tablename in self._schemas:
            return self._schemas[tablename]
        self._schemas[tablename] = schema
        self._tables[tablename] = Table(schema)
        self._manager.host_table(tablename, self._tables[tablename])

    def clear_table(self, tablename: str, schema) -> None:
        if tablename in self._tables:
            self._tables[tablename].clear()

    @app.get("/")
    async def site(self):
        return FileResponse(join(static_files_dir, "index.html"))

    @app.websocket("/ws")
    async def ws(self, ws: WebSocket):
        handler = PerspectiveStarletteHandler(manager=self._manager, websocket=ws)
        try:
            await handler.run()
        except WebSocketDisconnect:
            ...

    @app.get("/tables")
    async def tables(self):
        return list(self._schemas.keys())

    @app.post("/new/{tablename}")
    async def new_table_rest(self, tablename: str, request: Request) -> Response:
        if tablename in self._schemas:
            raise HTTPException(501, "Table already exists, replace not yet supported")

        try:
            schema = await request.json()
        except BaseException as exception:
            raise HTTPException(503, "Exception during schema parsing") from exception

        try:
            self.new_table(tablename, schema)
            return Response(content=schema)
        except BaseException as exception:
            raise HTTPException(
                503,
                f"Exception during table creation: {schema} / {tablename} / {format_exc()}",
            ) from exception

    @app.get("/get/{tablename}")
    async def get_table_rest(self, tablename: str):
        if tablename not in self._schemas:
            raise HTTPException(404, "Table does not exist: {tablename}")
        return Response(content=self._schemas[tablename])

    @app.post("/update/{tablename}")
    async def update_table_rest(self, tablename: str, request: Request) -> Response:
        if tablename not in self._schemas:
            # just create table for now
            self.new_table(tablename, [])
        try:
            data = await request.json()
        except BaseException as exception:
            raise HTTPException(503, "Exception during data parsing") from exception

        try:
            self.update(tablename, data)
        except BaseException as exception:
            raise HTTPException(503, f"Exception during data ingestion: {tablename} / {format_exc()}") from exception

    def update(self, tablename: str, data):
        if isinstance(data, dict):
            data = [data]
        self._tables[tablename].update(data)


@deployment(name="Perspective_Proxy_Server")
class PerspectiveProxyRayServer:
    def __init__(self, psp_handle):
        self._psp_handle = psp_handle

    def __call__(self, op, tablename, data_or_schema):
        if op == "new":
            if tablename and data_or_schema:
                self._psp_handle.new_table.remote(tablename, data_or_schema)
        if op == "update":
            if tablename and data_or_schema:
                self._psp_handle.update.remote(tablename, data_or_schema)
        if op == "clear":
            if tablename:
                self._psp_handle.clear_table.remote(tablename, data_or_schema)


def main(args: PerspectiveRayServerArgs = None) -> Application:
    args = args or PerspectiveRayServerArgs()
    if environ.get("RAY_SERVE_ENABLE_EXPERIMENTAL_STREAMING") is not None:
        return PerspectiveProxyRayServer.bind(PerspectiveRayServer.bind(args))
    raise Exception("Perspective server requires websockets, rerun with RAY_SERVE_ENABLE_EXPERIMENTAL_STREAMING=1")
