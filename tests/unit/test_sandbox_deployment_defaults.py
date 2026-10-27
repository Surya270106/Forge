from services.execution.sandbox import DockerSandbox


def test_docker_sandbox_disables_network_by_default(tmp_path):
    sandbox = DockerSandbox(workspace_root=str(tmp_path))
    assert sandbox.network_disabled is True
