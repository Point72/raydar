import json
import os
import pytest
import ray
import tempfile


class RayFixture(object):
    def __init__(self, config):
        self.config = config

    def __enter__(self):
        if ray.is_initialized():
            ray.shutdown()
        print(
            "Launching a Ray Cluster with config:\n",
            json.dumps(self.config, indent=4, default=lambda i: i.__name__),
        )

        context = ray.init(**self.config)
        if hasattr(context, "address_info"):
            os.environ["RAY_ADDRESS"] = context.address_info["address"]

    def __exit__(self, exc_type, exc_val, exc_tb):
        print("Shutting down Ray cluster!")
        if "RAY_ADDRESS" in os.environ:
            del os.environ["RAY_ADDRESS"]
        ray.shutdown()


@pytest.fixture(scope="module")
def unittest_ray_config():
    # Unit tests run on Jenkins, which may require special configuration
    # With the wrong configuration, it could mysteriously freeze
    config = dict(
        num_cpus=5,
        include_dashboard=True,
    )
    return config


@pytest.fixture(scope="module")
def unittest_ray_cluster(unittest_ray_config):
    with tempfile.TemporaryDirectory() as tmpdir:
        unittest_ray_config["storage"] = tmpdir
        with RayFixture(unittest_ray_config) as _:
            yield None
