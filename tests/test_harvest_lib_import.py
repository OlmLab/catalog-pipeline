"""R1-17: importing harvest_lib must not create harvest_cache/ in the cwd; the cache dir follows CATALOG_CACHE_DIR."""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_import_has_no_cwd_side_effect(tmp_path):
    env = {**os.environ, "PYTHONPATH": os.path.join(ROOT, "src"), "CATALOG_CACHE_DIR": str(tmp_path / "cache")}
    code = "import catalog.harvest.harvest_lib as HL; print(HL.CACHE_DIR)"
    p = subprocess.run([sys.executable, "-c", code], cwd=str(tmp_path), capture_output=True, text=True, env=env)
    assert p.returncode == 0, p.stderr
    assert not (tmp_path / "harvest_cache").exists()
    assert not (tmp_path / "cache").exists(), "cache dir must be created lazily, not at import"
    assert p.stdout.strip() == str(tmp_path / "cache" / "harvest_cache")
