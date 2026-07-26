import getpass
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from app.core.jwt_auth import hash_password


def main() -> int:
    password = getpass.getpass("请输入需要生成哈希的密码: ")
    confirmation = getpass.getpass("请再次输入密码: ")
    if password != confirmation:
        print("[FAIL] 两次输入的密码不一致")
        return 1
    if len(password) < 8:
        print("[FAIL] 演示账号密码至少需要8位")
        return 1
    print("\n密码哈希（可放入 AUTH_USERS_JSON，原始密码不会写入文件）:")
    print(hash_password(password))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
