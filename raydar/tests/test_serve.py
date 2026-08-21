import httpx
import pytest
import ray

from raydar.dashboard.serve import RaydarDeployment

PORT = 8899
BASE = f"http://127.0.0.1:{PORT}"


@pytest.fixture(scope="module")
def deployment(unittest_ray_cluster):
    ray.serve.start(http_options={"host": "127.0.0.1", "port": PORT})
    handle = ray.serve.run(RaydarDeployment.bind(), name="raydar", route_prefix="/")
    yield handle
    ray.serve.shutdown()


class TestRaydarDeployment:
    def test_the_app_is_built_on_the_replica(self, deployment):
        # Regression: passing the app to `ingress` makes Ray pickle it, which fails
        # on the Perspective server and the transports store it closes over.
        assert httpx.get(BASE + "/").status_code == 200

    def test_assets_are_served(self, deployment):
        for asset in ("/tree.json", "/js/cdn/index.js", "/components/perspective/cdn/index.js"):
            assert httpx.get(BASE + asset).status_code == 200, asset

    def test_apply_reaches_the_replica(self, deployment):
        deployment.apply.remote({"schemas": {"t": {"a": "integer"}}, "updates": {"t": [{"a": 1}]}}).result()
        assert httpx.get(BASE + "/").status_code == 200
