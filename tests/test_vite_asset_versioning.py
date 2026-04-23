import json
import unittest
from pathlib import Path

import codoxear.server as server


class TestViteAssetVersioning(unittest.TestCase):
    def test_asset_version_uses_manifest_hashes_when_present(self) -> None:
        manifest = {
            "index.html": {
                "file": "assets/main-abcd1234.js",
                "css": ["assets/main-efgh5678.css"],
            }
        }

        version = server._asset_version_from_manifest(manifest)

        self.assertEqual("abcd1234-efgh5678", version)

    def test_cache_control_marks_dist_assets_immutable(self) -> None:
        cache_control = server._cache_control_for_path(Path("web/dist/assets/main-abcd1234.js"))

        self.assertEqual("public, max-age=31536000, immutable", cache_control)

    def test_cache_control_keeps_non_asset_files_uncached(self) -> None:
        cache_control = server._cache_control_for_path(Path("codoxear/static/index.html"))

        self.assertEqual("no-store", cache_control)

    def test_asset_version_uses_stable_fallback_for_unhashed_manifest_entries(self) -> None:
        manifest = {
            "index.html": {
                "file": "assets/main.js",
                "css": ["assets/main.css"],
            }
        }

        version = server._asset_version_from_manifest(manifest)

        self.assertNotEqual("dev", version)

if __name__ == "__main__":
    unittest.main()
