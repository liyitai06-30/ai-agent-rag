# -*- coding: utf-8 -*-
"""让 app 包在被导入时自动加载项目根目录的 .env。
为什么需要它：Python 不会自动读 .env。上游项目靠 shell 里 export 环境变量，
所以直接双击 bat 启动时，.env 里的配置一个字都不会生效。
覆盖位置：evidenceqa/app/__init__.py（原文件是空的，替换掉没有副作用）
"""
import os
from pathlib import Path
def _load_dotenv() -> None:
    here = Path(__file__).resolve()
    candidates = [parent / ".env" for parent in list(here.parents)[:4]]
    candidates.append(Path.cwd() / ".env")
    for path in candidates:
        if not path.is_file():
            continue
        try:
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key:
                    os.environ.setdefault(key, value)
        except OSError:
            pass
        return
_load_dotenv()