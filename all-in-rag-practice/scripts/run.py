"""使用 uv 启动教程中的交互式菜谱问答系统。"""

import os
import sys

from runtime import PROJECT_ROOT, load_config, prepare_environment


def main():
    prepare_environment()
    if not os.getenv("MOONSHOT_API_KEY", "").strip():
        print(
            f"请将 {PROJECT_ROOT / '.env.example'} 复制为 .env，"
            "并填写 MOONSHOT_API_KEY。",
            file=sys.stderr,
        )
        return 1

    from main import RecipeRAGSystem

    RecipeRAGSystem(load_config()).run_interactive()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
