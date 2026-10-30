"""Unregistered image files count as indexing work for run submission (#712)."""
import pytest
from PIL import Image

from modules import db
from modules.run_phase_planner import scope_has_unregistered_files

pytestmark = pytest.mark.postgres


@pytest.fixture(autouse=True)
def _clean(postgres_test_session, clean_postgres):
    yield


def test_only_unregistered_supported_images_count(tmp_path):
    folder = tmp_path / "fresh"
    folder.mkdir()
    assert not scope_has_unregistered_files([str(folder.resolve())])         # empty folder
    (folder / "notes.txt").write_text("not an image")
    assert not scope_has_unregistered_files([str(folder.resolve())])         # unsupported extension
    image = folder / "a.jpg"
    Image.new("RGB", (64, 48), (1, 2, 3)).save(image)
    assert scope_has_unregistered_files([str(folder.resolve())])
    db.get_connector().execute("INSERT INTO images (file_path) VALUES (?)", (str(image),))
    assert not scope_has_unregistered_files([str(folder.resolve())])         # registered now
