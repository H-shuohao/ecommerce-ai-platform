import argparse
import os
import sys
from pathlib import Path

from dotenv import dotenv_values


PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from services.deployment_config_service import validate_deployment_config


def main() -> int:
    parser = argparse.ArgumentParser(
        description="启动前检查部署配置，不输出任何密钥内容。",
    )
    parser.add_argument(
        "--env-file",
        default=str(PROJECT_DIR / ".env"),
        help="需要检查的环境变量文件，默认 services/ai-core/.env",
    )
    parser.add_argument(
        "--production",
        action="store_true",
        help="启用生产模式安全检查。",
    )
    args = parser.parse_args()

    env_path = Path(args.env_file).resolve()
    if not env_path.is_file():
        print(f"[FAIL] 环境变量文件不存在: {env_path}")
        return 1

    file_values = {
        key: value or ""
        for key, value in dotenv_values(env_path).items()
    }
    environment = {**file_values, **os.environ}
    result = validate_deployment_config(
        environment,
        production=args.production,
    )

    mode = "生产" if args.production else "本地"
    print(f"部署配置检查（{mode}模式）")
    for warning in result.warnings:
        print(f"[WARN] {warning}")
    for error in result.errors:
        print(f"[FAIL] {error}")
    if result.passed:
        print("[PASS] 部署所需核心配置检查通过")
        return 0
    print(f"[FAIL] 共发现 {len(result.errors)} 项阻塞问题")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
