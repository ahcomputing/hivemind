from pathlib import Path


def test_production_image_includes_only_the_operator_schedule_importer():
    """The documented kubectl exec command must work in the published image."""
    dockerfile = Path("Dockerfile").read_text()
    assert "COPY scripts/import_official_events.py ./scripts/import_official_events.py" in dockerfile
    assert "COPY scripts ./scripts" not in dockerfile
