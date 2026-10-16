"""源码目录中的兼容入口：python -m cli import examples/chat_sample.json。"""

from wechat_archive.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
