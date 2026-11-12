"""验证直接入口和 uv 启动入口在不同工作目录下定位同一份项目资源。"""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = PROJECT_ROOT / "code" / "C8"


class WorkingDirectoryTests(unittest.TestCase):
    def test_entry_points_resolve_resources_from_any_directory(self):
        program = """
import json
from pathlib import Path
from config import RAGConfig
from main import RecipeRAGSystem
from runtime import load_config, prepare_environment

cwd = Path.cwd()
direct = RecipeRAGSystem()
prepare_environment()
wrapped = RecipeRAGSystem(load_config())
print(json.dumps({
    'direct': direct.config.to_dict(),
    'wrapped': wrapped.config.to_dict(),
    'default': RAGConfig().to_dict(),
    'cwd_unchanged': cwd == Path.cwd(),
}))
"""
        env = dict(os.environ)
        env.update(
            {
                "PYTHONPATH": os.pathsep.join(
                    (str(CODE_DIR), str(PROJECT_ROOT / "scripts"))
                ),
                "LLM_MODEL": "local-test-model",
                "LLM_API_KEY": "local-test-key",
                "LLM_BASE_URL": "http://127.0.0.1:9/v1",
            }
        )
        with TemporaryDirectory() as temporary:
            for cwd in (PROJECT_ROOT, CODE_DIR, PROJECT_ROOT.parent, Path(temporary)):
                with self.subTest(cwd=cwd):
                    result = subprocess.run(
                        [sys.executable, "-c", program],
                        cwd=cwd,
                        env=env,
                        capture_output=True,
                        text=True,
                        check=True,
                        timeout=30,
                    )
                    actual = json.loads(result.stdout)
                    self.assertTrue(actual["cwd_unchanged"])
                    for entry in ("direct", "wrapped", "default"):
                        self.assertEqual(
                            actual[entry]["data_path"],
                            str(PROJECT_ROOT / "data" / "C8" / "cook"),
                        )
                        self.assertEqual(
                            actual[entry]["index_save_path"],
                            str(CODE_DIR / "vector_index"),
                        )
                    self.assertEqual(actual["direct"], actual["wrapped"])


if __name__ == "__main__":
    unittest.main()
