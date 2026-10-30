import pytest

from modules.visual_evidence.cache import EvidenceCache


def test_atomic_cache_is_scoped_and_survives_restart(tmp_path):
    cache = EvidenceCache(tmp_path)
    key = "a" * 64
    artifact = cache.write_artifact(42, key, b"PNG bytes", "png")
    cache.put(42, key, "sharpness", {"artifacts": {"image": artifact}})
    restarted = EvidenceCache(tmp_path)
    assert restarted.get(42, key, "sharpness")["artifacts"]["image"] == artifact
    assert restarted.artifact(42, artifact).read_bytes() == b"PNG bytes"
    with pytest.raises(FileNotFoundError):
        restarted.artifact(43, artifact)
    for attack in ("../../config.json", "/etc/passwd", "a" * 64 + "_../x.png"):
        with pytest.raises((ValueError, FileNotFoundError)):
            restarted.artifact(42, attack)


def test_eviction_protects_active_bundle_and_missing_files_invalidate_entries(tmp_path):
    cache = EvidenceCache(tmp_path, max_bytes=1200)
    old, current = "a" * 64, "b" * 64
    first = cache.write_artifact(1, old, b"a" * 800, "png")
    cache.put(1, old, "mask", {"artifacts": {"mask": first}})
    with cache.pin(1, current):
        second = cache.write_artifact(1, current, b"b" * 800, "png")
        cache.put(1, current, "mask", {"artifacts": {"mask": second}})
        cache.prune()
        assert cache.artifact(1, second).exists()
        assert cache.get(1, old, "mask") is None
    cache.artifact(1, second).unlink()
    assert cache.get(1, current, "mask") is None
