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

# ─── 防火墙配置 ────────────────────────────────────────
configure_firewall() {
    step "配置防火墙..."

    # 检测防火墙类型
    if command -v firewall-cmd &>/dev/null && systemctl is-active --quiet firewalld; then
        # firewalld (CentOS/RHEL/Fedora)
        info "检测到 firewalld，正在配置..."
        firewall-cmd --permanent --add-port=9000/tcp
        firewall-cmd --permanent --add-port=8991/tcp
        firewall-cmd --reload
        info "firewalld 规则已添加 ✓"
    elif command -v ufw &>/dev/null; then
        # ufw (Ubuntu/Debian)
        info "检测到 ufw，正在配置..."
        ufw allow 9000/tcp comment "Kiro Gateway API"
        ufw allow 8991/tcp comment "Kiro Gateway UI"
        info "ufw 规则已添加 ✓"
    elif command -v iptables &>/dev/null; then
        # iptables (通用)
        info "使用 iptables 配置..."
        iptables -I INPUT -p tcp --dport 9000 -j ACCEPT
        iptables -I INPUT -p tcp --dport 8991 -j ACCEPT

        # 尝试保存规则
        if command -v iptables-save &>/dev/null; then
            if [[ -f /etc/sysconfig/iptables ]]; then
                iptables-save > /etc/sysconfig/iptables
            elif [[ -f /etc/iptables/rules.v4 ]]; then
                iptables-save > /etc/iptables/rules.v4
            fi
        fi
        info "iptables 规则已添加 ✓"
    else
        warn "未检测到防火墙，跳过配置"
        warn "如需公网访问，请手动开放端口 9000 和 8991"
    fi
}

# ─── 停止服务 ──────────────────────────────────────────
stop_services() {
    step "停止现有服务..."
    local stopped=false

    for svc in "$SERVICE_UI" "$SERVICE_BACKEND"; do
        if systemctl is-active --quiet "$svc" 2>/dev/null; then
            systemctl stop "$svc"
            info "已停止 $svc"
            stopped=true
        fi
    done

    # 额外检查并杀掉可能残留的进程
    local pids
    pids=$(pgrep -f "kiro-gateway|main.py" || true)
    if [[ -n "$pids" ]]; then
        warn "发现残留进程，正在清理..."
        pkill -f "kiro-gateway|main.py" || true
        sleep 1
        # 强制杀掉仍然存在的进程
        pkill -9 -f "kiro-gateway|main.py" || true
        info "残留进程已清理"
        stopped=true
    fi

    if [[ "$stopped" == false ]]; then
        info "没有运行中的服务"
    fi
}

# ─── 依赖安装 ──────────────────────────────────────────
setup_venv() {
    step "设置 Python 虚拟环境..."
    if [[ ! -d "$VENV_DIR" ]]; then
        python3 -m venv "$VENV_DIR"
        info "虚拟环境已创建"
    fi
    info "更新 Python 依赖..."
    "$VENV_DIR/bin/pip" install --upgrade pip -q
    "$VENV_DIR/bin/pip" install -r "$PROJECT_DIR/requirements.txt" --upgrade -q
    info "Python 依赖更新完成 ✓"
}

setup_frontend() {
    step "设置前端..."
    local ui_dir="$PROJECT_DIR/task-ui"
    if [[ ! -d "$ui_dir" ]]; then
        warn "task-ui 目录不存在，跳过"
        return 1
    fi

    # 更新依赖
    info "更新前端依赖..."
    (cd "$ui_dir" && npm install --silent)

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
ExecStart=$VENV_DIR/bin/python main.py --port 9000
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
    local npx_path node_path node_dir
    npx_path="$(command -v npx)"
    node_path="$(command -v node)"
    node_dir="$(dirname "$node_path")"

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
Environment="PATH=$node_dir:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
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
    step "启用并重启服务..."

    systemctl enable "$SERVICE_BACKEND"
    systemctl restart "$SERVICE_BACKEND"
    info "$SERVICE_BACKEND 已启用并重启 ✓"

    if [[ -f "$SYSTEMD_DIR/$SERVICE_UI" ]]; then
        systemctl enable "$SERVICE_UI"
        systemctl restart "$SERVICE_UI"
        info "$SERVICE_UI 已启用并重启 ✓"
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
    echo

    # 清理防火墙规则
    step "清理防火墙规则..."
    if command -v firewall-cmd &>/dev/null && systemctl is-active --quiet firewalld; then
        firewall-cmd --permanent --remove-port=9000/tcp 2>/dev/null || true
        firewall-cmd --permanent --remove-port=8991/tcp 2>/dev/null || true
        firewall-cmd --reload
        info "firewalld 规则已清理"
    elif command -v ufw &>/dev/null; then
        ufw delete allow 9000/tcp 2>/dev/null || true
        ufw delete allow 8991/tcp 2>/dev/null || true
        info "ufw 规则已清理"
    elif command -v iptables &>/dev/null; then
        iptables -D INPUT -p tcp --dport 9000 -j ACCEPT 2>/dev/null || true
        iptables -D INPUT -p tcp --dport 8991 -j ACCEPT 2>/dev/null || true
        info "iptables 规则已清理"
    fi

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

    # 1. 停止现有服务
    stop_services
    echo

    # 2. 检查环境
    check_python
    echo

    # 3. 更新 Python 依赖
    setup_venv
    echo

    # 4. 更新前端依赖并构建
    HAS_NODE=false
    if check_node; then
        HAS_NODE=true
        echo
        setup_frontend || HAS_NODE=false
    fi
    echo

    # 5. 生成服务文件
    generate_backend_service
    if [[ "$HAS_NODE" == true ]]; then
        generate_ui_service
    fi
    echo

    # 6. 安装服务
    install_services
    echo

    # 7. 配置防火墙
    configure_firewall
    echo

    # 8. 重启服务
    enable_and_start
    echo

    # 清理临时文件
    rm -f "/tmp/$SERVICE_BACKEND" "/tmp/$SERVICE_UI"

    # 获取服务器 IP 地址
    local server_ip
    server_ip=$(hostname -I | awk '{print $1}')
    if [[ -z "$server_ip" ]]; then
        server_ip=$(ip route get 1 | awk '{print $7; exit}' 2>/dev/null || echo "localhost")
    fi

    info "========================================="
    info "  安装完成！"
    info "========================================="
    echo
    info "服务状态:"
    info "  后端服务: systemctl status $SERVICE_BACKEND"
    if [[ "$HAS_NODE" == true ]]; then
        info "  前端服务: systemctl status $SERVICE_UI"
    fi
    info "  查看日志: journalctl -u $SERVICE_BACKEND -f"
    echo
    info "访问地址:"
    info "  后端 API: http://$server_ip:9000"
    if [[ "$HAS_NODE" == true ]]; then
        info "  前端管理: http://$server_ip:8991"
        echo
        info "首次访问前端需要导入凭据："
        info "  1. 浏览器打开 http://$server_ip:8991"
        info "  2. 点击「导入凭据」按钮"
        info "  3. 上传 .env 文件或手动输入配置"
    fi
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
