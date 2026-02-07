#!/bin/bash
# Kiro Tools TUI 启动脚本

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 检查虚拟环境是否存在
if [ ! -d ".venv" ]; then
    echo "⚠️  虚拟环境不存在，正在运行安装脚本..."
    ./install.sh
    if [ $? -ne 0 ]; then
        echo "❌ 安装失败，请检查错误信息"
        exit 1
    fi
fi

# 激活虚拟环境
source "$SCRIPT_DIR/.venv/bin/activate"

# 检查关键依赖是否已安装
if ! python3 -c "import textual" 2>/dev/null; then
    echo "⚠️  依赖未安装，正在运行安装脚本..."
    ./install.sh
    if [ $? -ne 0 ]; then
        echo "❌ 安装失败，请检查错误信息"
        exit 1
    fi
    # 重新激活虚拟环境
    source "$SCRIPT_DIR/.venv/bin/activate"
fi

# 运行应用
python3 "$SCRIPT_DIR/kiro_tools_tui.py"
