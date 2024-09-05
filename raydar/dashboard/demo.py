import os
import random
import ray
import starlette
import time

from .server import PerspectiveProxyRayServer, PerspectiveRayServer


@ray.remote
def test_job(backoff, tablename, proxy):
    start = time.time()
    time.sleep(backoff)
    end = time.time()
    runtime = end - start
    data = dict(start=start, end=end, runtime=runtime, backoff=backoff, random=random.random())
    return proxy.remote("update", tablename, data)


if __name__ == "__main__":
    os.environ["RAY_SERVE_ENABLE_EXPERIMENTAL_STREAMING"] = "1"

    host = "127.0.0.1"  # NOTE: change if you run on another machine
    port = 8989
    ray.init(dashboard_host=host, dashboard_port=port, runtime_env={"py_modules": [starlette]})
    ray.serve.start(http_options={"host": host, "port": port})

    webserver = ray.serve.run(PerspectiveRayServer.bind(), name="webserver", route_prefix="/")
    proxy_server = ray.serve.run(PerspectiveProxyRayServer.bind(webserver), name="proxy", route_prefix="/proxy")

    # setup perspective table
    proxy_server.remote(
        "new",
        "data",
        {
            "start": "datetime",
            "end": "datetime",
            "runtime": "float",
            "backoff": "float",
            "random": "float",
        },
    )

    # launch jobs
    while True:
        test_job.remote(backoff=random.random(), tablename="data", proxy=proxy_server)
        time.sleep(0.5)
