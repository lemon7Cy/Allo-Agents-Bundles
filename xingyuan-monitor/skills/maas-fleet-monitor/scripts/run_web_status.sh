#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -x ".venv/bin/python" ]; then
  exec ".venv/bin/python" "scripts/web_status.py" "$@"
fi

if command -v python3 >/dev/null 2>&1; then
  exec python3 "scripts/web_status.py" "$@"
fi

if [ "${1:-}" = "--format" ] && [ "${2:-}" = "monitor-card" ]; then
  printf '%s\n' \
    '状态：数据不足' \
    '范围：MaaS public-maas，当前查询' \
    '信号：未找到可执行的 Python 运行时。' \
    '诊断：skill 无法启动 web_status.py。' \
    '建议：安装 python3，或在 skill 目录创建 .venv 并安装 requirements.txt。' \
    '缺口：本次不输出指标行，避免写入伪造观测。'
else
  printf '{"error":"python_not_found","hint":"Install python3 or create .venv with requirements.txt"}\n'
fi
exit 2
