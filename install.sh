#!/bin/bash

# Kiro Gateway — systemd 安装脚本
# 用法:
#   ./install.sh              安装并启动服务
#   ./install.sh --uninstall  停止、禁用、删除服务
#   ./install.sh --status     查看服务状态

set -euo pipefail

# ─── 常量 ───────────────────────────────────────────────
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
SERVICE_BACKEND="kiro-gateway.service"
SERVICE_UI="kiro-gateway-ui.service"
SYSTEMD_DIR="/etc/systemd/system"
# 获取实际用户（sudo 场景下取 SUDO_USER）
CURRENT_USER="${SUDO_USER:-$(whoami)}"
CURRENT_GROUP="$(id -gn "$CURRENT_USER")"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }
step()  { echo -e "${BLUE}[STEP]${NC} $1"; }

# ─── 环境检查 ───────────────────────────────────────────
check_root() {
    if [[ $EUID -ne 0 ]]; then
        error "此脚本需要 root 权限，请使用 sudo 运行"
        echo "  sudo $0 $*"
        exit 1
    fi
}

check_python() {
    step "检查 Python 环境..."
    if ! command -v python3 &>/dev/null; then
        error "未找到 Python3，请先安装 Python 3.10+"
        exit 1
    fi
    local ver
    ver=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    if ! python3 -c 'import sys; exit(0 if sys.version_info >= (3, 10) else 1)'; then
        error "需要 Python 3.10+，当前: $ver"
        exit 1
    fi
    info "Python $ver ✓"
}
check_node() {
    step "检查 Node.js 环境..."
    if ! command -v node &>/dev/null; then
        warn "未找到 Node.js，将跳过前端服务安装"
        return 1
    fi
    if ! command -v npm &>/dev/null; then
        warn "未找到 npm，将跳过前端服务安装"
        return 1
    fi
    info "Node $(node -v) / npm $(npm -v) ✓"
    return 0
}

# ─── 依赖安装 ──────────────────────────────────────────
setup_venv() {
    step "设置 Python 虚拟环境..."
    if [[ ! -d "$VENV_DIR" ]]; then
        python3 -m venv "$VENV_DIR"
        info "虚拟环境已创建"
    fi
    info "安装 Python 依赖..."
    "$VENV_DIR/bin/pip" install --upgrade pip -q
    "$VENV_DIR/bin/pip" install -r "$PROJECT_DIR/requirements.txt" -q
    info "Python 依赖安装完成 ✓"
}

setup_frontend() {
    step "设置前端..."
    local ui_dir="$PROJECT_DIR/task-ui"
    if [[ ! -d "$ui_dir" ]]; then
        warn "task-ui 目录不存在，跳过"
        return 1
    fi

    # 安装依赖
    if [[ ! -d "$ui_dir/node_modules" ]]; then
        info "安装前端依赖..."
        (cd "$ui_dir" && npm install --silent)
    fi

    # 构建生产版本
    info "构建前端生产版本..."
    (cd "$ui_dir" && npx vite build)
    info "前端构建完成 → task-ui/dist/ ✓"
    return 0
}

# ─── 生成 systemd 服务文件 ─────────────────────────────
generate_backend_service() {
    step "生成后端服务文件..."
    cat > "/tmp/$SERVICE_BACKEND" <<EOF
[Unit]
Description=Kiro Gateway - OpenAI-compatible API Gateway
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$CURRENT_USER
Group=$CURRENT_GROUP
WorkingDirectory=$PROJECT_DIR
EnvironmentFile=-$PROJECT_DIR/.env
ExecStart=$VENV_DIR/bin/python main.py
Restart=on-failure
RestartSec=5
StartLimitIntervalSec=60
StartLimitBurst=5

# 安全加固
NoNewPrivileges=true
ProtectSystem=full
PrivateTmp=true

# 日志
StandardOutput=journal
StandardError=journal
SyslogIdentifier=kiro-gateway

[Install]
WantedBy=multi-user.target
EOF
    info "后端服务文件已生成 ✓"
}

generate_ui_service() {
    step "生成前端服务文件..."
    local npx_path
    npx_path="$(command -v npx)"
    cat > "/tmp/$SERVICE_UI" <<EOF
[Unit]
Description=Kiro Gateway Task UI
After=kiro-gateway.service
Wants=kiro-gateway.service

[Service]
Type=simple
User=$CURRENT_USER
Group=$CURRENT_GROUP
WorkingDirectory=$PROJECT_DIR/task-ui
ExecStart=$npx_path vite --host 0.0.0.0 --port 8991
Restart=on-failure
RestartSec=5
StartLimitIntervalSec=60
StartLimitBurst=5

# 安全加固
NoNewPrivileges=true
ProtectSystem=full
PrivateTmp=true

# 日志
StandardOutput=journal
StandardError=journal
SyslogIdentifier=kiro-gateway-ui

[Install]
WantedBy=multi-user.target
EOF
    info "前端服务文件已生成 ✓"
}

# ─── 安装服务 ──────────────────────────────────────────
install_services() {
    step "安装 systemd 服务..."

    cp "/tmp/$SERVICE_BACKEND" "$SYSTEMD_DIR/$SERVICE_BACKEND"
    info "已安装 $SERVICE_BACKEND"

    if [[ -f "/tmp/$SERVICE_UI" ]]; then
        cp "/tmp/$SERVICE_UI" "$SYSTEMD_DIR/$SERVICE_UI"
        info "已安装 $SERVICE_UI"
    fi

    systemctl daemon-reload
    info "systemd 配置已重载 ✓"
}

enable_and_start() {
    step "启用并启动服务..."

    systemctl enable "$SERVICE_BACKEND"
    systemctl start "$SERVICE_BACKEND"
    info "$SERVICE_BACKEND 已启用并启动 ✓"

    if [[ -f "$SYSTEMD_DIR/$SERVICE_UI" ]]; then
        systemctl enable "$SERVICE_UI"
        systemctl start "$SERVICE_UI"
        info "$SERVICE_UI 已启用并启动 ✓"
    fi
}

# ─── 卸载 ─────────────────────────────────────────────
do_uninstall() {
    step "卸载 Kiro Gateway 服务..."

    for svc in "$SERVICE_UI" "$SERVICE_BACKEND"; do
        if [[ -f "$SYSTEMD_DIR/$svc" ]]; then
            systemctl stop "$svc" 2>/dev/null || true
            systemctl disable "$svc" 2>/dev/null || true
            rm -f "$SYSTEMD_DIR/$svc"
            info "已移除 $svc"
        fi
    done

    systemctl daemon-reload
    info "卸载完成 ✓"
}

# ─── 状态查看 ──────────────────────────────────────────
do_status() {
    echo
    for svc in "$SERVICE_BACKEND" "$SERVICE_UI"; do
        if [[ -f "$SYSTEMD_DIR/$svc" ]]; then
            echo -e "${BLUE}── $svc ──${NC}"
            systemctl status "$svc" --no-pager -l 2>/dev/null || true
            echo
        fi
    done
}

# ─── 主流程 ────────────────────────────────────────────
do_install() {
    echo
    info "========================================="
    info "  Kiro Gateway — systemd 安装"
    info "========================================="
    echo

    check_python
    echo
    setup_venv
    echo

    HAS_NODE=false
    if check_node; then
        HAS_NODE=true
        echo
        setup_frontend || HAS_NODE=false
    fi
    echo

    generate_backend_service
    if [[ "$HAS_NODE" == true ]]; then
        generate_ui_service
    fi
    echo

    install_services
    echo
    enable_and_start
    echo

    # 清理临时文件
    rm -f "/tmp/$SERVICE_BACKEND" "/tmp/$SERVICE_UI"

    info "========================================="
    info "  安装完成！"
    info "========================================="
    echo
    info "后端服务: systemctl status $SERVICE_BACKEND"
    if [[ "$HAS_NODE" == true ]]; then
        info "前端服务: systemctl status $SERVICE_UI"
    fi
    info "查看日志: journalctl -u $SERVICE_BACKEND -f"
    echo
    info "管理命令:"
    info "  sudo $0 --status     查看状态"
    info "  sudo $0 --uninstall  卸载服务"
    echo
}

# ─── 入口 ──────────────────────────────────────────────
main() {
    case "${1:-}" in
        --uninstall)
            check_root "$@"
            do_uninstall
            ;;
        --status)
            check_root "$@"
            do_status
            ;;
        --help|-h)
            echo "用法: sudo $0 [选项]"
            echo
            echo "选项:"
            echo "  (无参数)      安装并启动服务"
            echo "  --uninstall   停止、禁用、删除服务"
            echo "  --status      查看服务状态"
            echo "  --help        显示此帮助"
            ;;
        *)
            check_root "$@"
            do_install
            ;;
    esac
}

main "$@"
