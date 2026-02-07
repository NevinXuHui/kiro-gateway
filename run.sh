#!/bin/bash

# Kiro Gateway 启动脚本
# 用法: ./run.sh [--port PORT] [--host HOST]

set -e

# 虚拟环境目录
VENV_DIR=".venv"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印带颜色的消息
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

# 检查 Python 版本
check_python() {
    print_step "检查 Python 环境..."

    if ! command -v python3 &> /dev/null; then
        print_error "未找到 Python3，请先安装 Python 3.10+"
        exit 1
    fi

    PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    print_info "Python 版本: $PYTHON_VERSION"

    # 检查版本是否 >= 3.10
    if ! python3 -c 'import sys; exit(0 if sys.version_info >= (3, 10) else 1)'; then
        print_error "需要 Python 3.10 或更高版本，当前版本: $PYTHON_VERSION"
        exit 1
    fi
}

# 设置虚拟环境
setup_venv() {
    print_step "设置虚拟环境..."

    # 检查是否已在虚拟环境中
    if [ -n "$VIRTUAL_ENV" ]; then
        print_info "已在虚拟环境中: $VIRTUAL_ENV"
        return 0
    fi

    # 检查虚拟环境是否存在
    if [ ! -d "$VENV_DIR" ]; then
        print_info "创建虚拟环境: $VENV_DIR"
        python3 -m venv "$VENV_DIR"
        print_info "虚拟环境创建成功"
    else
        print_info "虚拟环境已存在: $VENV_DIR"
    fi

    # 激活虚拟环境
    print_info "激活虚拟环境..."
    source "$VENV_DIR/bin/activate"

    # 验证激活成功
    if [ -n "$VIRTUAL_ENV" ]; then
        print_info "虚拟环境激活成功: $VIRTUAL_ENV"
    else
        print_error "虚拟环境激活失败"
        exit 1
    fi

    # 升级 pip
    print_info "升级 pip..."
    pip install --upgrade pip -q
}

# 检查并安装依赖
install_dependencies() {
    print_step "检查依赖..."

    # 检查多个关键依赖
    MISSING_DEPS=false
    for module in fastapi uvicorn httpx loguru dotenv tiktoken; do
        if ! python -c "import ${module}" 2>/dev/null; then
            MISSING_DEPS=true
            break
        fi
    done

    if [ "$MISSING_DEPS" = true ]; then
        print_warn "依赖未完全安装，正在安装..."
        pip install -r requirements.txt
        print_info "依赖安装完成"
    else
        print_info "所有依赖已安装"
    fi
}

# 检查配置文件
check_config() {
    print_step "检查配置文件..."

    if [ ! -f ".env" ]; then
        print_warn ".env 文件不存在"
        if [ -f ".env.example" ]; then
            print_info "从 .env.example 创建 .env 文件..."
            cp .env.example .env
            echo
            print_warn "⚠️  请编辑 .env 文件并配置你的凭证！"
            print_warn "⚠️  至少需要设置 PROXY_API_KEY 和一个认证选项"
            echo
            read -p "按回车键继续，或 Ctrl+C 取消..."
        else
            print_error ".env.example 文件也不存在！"
            exit 1
        fi
    else
        print_info "配置文件存在"
    fi
}

# 主函数
main() {
    echo
    print_info "========================================="
    print_info "    Kiro Gateway 启动脚本"
    print_info "========================================="
    echo

    # 执行检查和设置
    check_python
    echo
    setup_venv
    echo
    install_dependencies
    echo
    check_config

    echo
    print_info "========================================="
    print_info "    启动服务器..."
    print_info "========================================="
    echo

    # 传递所有参数给 main.py
    python main.py "$@"
}

# 运行主函数
main "$@"
