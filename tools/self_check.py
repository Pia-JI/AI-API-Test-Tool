"""命令行自检脚本（开发环境使用）。

用法：
    python tools/self_check.py --base-url http://127.0.0.1:8899/v1 --api-key test --count 5

完整参数见 python tools/self_check.py --help。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.selfcheck import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
