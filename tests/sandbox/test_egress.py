import pytest

from loadline.adapters.runtime.docker_runner import create_internal_network, docker_cmd, egress_check, probe_image


@pytest.mark.integration
def test_internal_network_blocks_egress():
    name = f"loadline-test-{__import__('uuid').uuid4().hex[:8]}"
    err = create_internal_network(name)
    assert err is None
    try:
        assert egress_check(probe_image(), name)
    finally:
        docker_cmd(["network", "rm", name])
