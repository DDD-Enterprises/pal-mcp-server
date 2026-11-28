from pathlib import Path

import pytest
import yaml


def _volume_target(volume):
    if isinstance(volume, str):
        parts = volume.split(":")
        return parts[1] if len(parts) > 1 else None
    if isinstance(volume, dict):
        return volume.get("target")
    return None


def test_compose_does_not_shadow_image_model_catalogs():
    compose = yaml.safe_load((Path(__file__).parents[1] / "docker-compose.yml").read_text())
    volumes = compose["services"]["pal-mcp"].get("volumes", [])

    assert all(_volume_target(volume) != "/app/conf" for volume in volumes)


def test_volume_target_handles_short_and_long_compose_syntax():
    assert _volume_target("./conf:/app/conf:ro") == "/app/conf"
    assert _volume_target({"type": "bind", "source": "./conf", "target": "/app/conf"}) == "/app/conf"


def test_requirements_support_responses_api():
    requirements = (Path(__file__).parents[1] / "requirements.txt").read_text()
    project = (Path(__file__).parents[1] / "pyproject.toml").read_text()

    assert "openai>=1.66.0" in requirements
    assert '"openai>=1.66.0"' in project


@pytest.mark.parametrize("mode", ["foreign", "multiple", "isolated", "empty"])
def test_workstation_deployment_isolates_ownership_before_launch(tmp_path, mode):
    """Exercise the real wrapper with fake executables, never Docker or Keychain."""
    import json
    import os
    import subprocess
    import sys

    log = tmp_path / "calls.jsonl"
    docker = tmp_path / "docker"
    docker.write_text(
        f"#!{sys.executable}\n"
        "import json,os,sys\n"
        "from pathlib import Path\n"
        "args=sys.argv[1:];mode=os.environ['STUB_MODE']\n"
        "with open(os.environ['STUB_LOG'],'a') as f:f.write(json.dumps({'docker':args})+'\\n')\n"
        "if args[:2]==['ps','-aq']:\n"
        " if any('label=' in a for a in args):\n"
        "  print('one\\ntwo' if mode=='multiple' else 'one' if mode=='isolated' else '')\n"
        " else: print('one' if mode in ['foreign','isolated'] else '')\n"
        "elif args and args[0]=='inspect':\n"
        " print(('dopemux' if mode=='foreign' else 'dopemux-pal-kimi')+'|pal-stdio')\n"
    )
    dopemux = tmp_path / "dopemux"
    dopemux.write_text(
        f"#!{sys.executable}\n"
        "import json,os,sys\n"
        "from pathlib import Path\n"
        "with open(os.environ['STUB_LOG'],'a') as f:\n"
        " f.write(json.dumps({'dopemux':sys.argv[1:],'project':os.getenv('COMPOSE_PROJECT_NAME'),"
        "'compose_present':Path('compose.yml').is_file()})+'\\n')\n"
    )
    security = tmp_path / "security"
    security.write_text(f"#!{sys.executable}\nraise AssertionError('Keychain must not be read in this fixture')\n")
    for executable in [docker, dopemux, security]:
        executable.chmod(0o755)
    env = dict(os.environ, PATH=str(tmp_path) + os.pathsep + os.environ["PATH"], STUB_MODE=mode, STUB_LOG=str(log))
    for key in ["CHEAPERINFERENCE", "OPENROUTER", "OPENAI", "GEMINI", "XAI", "ANTHROPIC"]:
        env[key + "_API_KEY"] = "fixture-only"
    wrapper = Path(__file__).parents[1] / "scripts/pal-stdio-compose"
    result = subprocess.run(["bash", str(wrapper)], env=env, capture_output=True, text=True, timeout=10)
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    launched = [call for call in calls if "dopemux" in call]
    if mode in ["foreign", "multiple"]:
        assert result.returncode != 0
        assert not launched
    else:
        assert result.returncode == 0, result.stderr
        assert launched == [
            {
                "dopemux": ["mcp", "up", "--services", "pal-stdio"],
                "project": "dopemux-pal-kimi",
                "compose_present": True,
            }
        ]
    assert not any(call.get("docker", [])[:1] == ["compose"] for call in calls)
