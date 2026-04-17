import sys
"""提交信息中文映射过滤脚本。

用途：
- 在 stdin 读入完整 commit message；
- 如果首行（subject）命中 mapping，则替换为中文；
- 其余正文原样保留输出到 stdout。
"""


mapping = {
    "feat: add URL-to-eink agent flow MVP": "feat: 实现 URL 到墨屏的 Agent Flow MVP",
    "feat: add .env.example and auto-load .env": "feat: 增加 .env 示例并自动加载",
    "feat: support direct text input and add eink cover placeholder": "feat: 支持纯文本直通并加入墨屏封面占位",
    "fix: lazy import bs4 for direct text input": "fix: 仅在 URL 路径才懒加载 bs4（支持纯文本直通）",
}


def main() -> None:
    """脚本主入口：执行“读入 -> 匹配 -> 替换 -> 输出”流程。"""
    msg = sys.stdin.read()
    if not msg:
        return

    lines = msg.splitlines()
    if not lines:
        sys.stdout.write(msg)
        return

    subject = lines[0]
    if subject in mapping:
        lines[0] = mapping[subject]
        sys.stdout.write("\n".join(lines))
    else:
        sys.stdout.write(msg)


if __name__ == "__main__":
    main()

