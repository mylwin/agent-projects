"""使用 uv 启动教程中的交互式菜谱问答系统。"""

import sys

from runtime import PROJECT_ROOT, load_config, prepare_environment


def main():
    prepare_environment()
    config = load_config()
    try:
        config.validate_llm()
    except ValueError as error:
        print(
            f"请将 {PROJECT_ROOT / '.env.example'} 复制为 .env，"
            f"并填写模型配置。{error}",
            file=sys.stderr,
        )
        return 1

    from main import RecipeRAGSystem

    RecipeRAGSystem(config).run_interactive()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
