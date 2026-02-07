#!/usr/bin/env python3
"""
Kiro Gateway 工具集 - 整合 TUI 版本

包含以下功能：
1. Token 转换工具
2. 认证切换工具
"""

import json
import requests
import cbor2
import uuid
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll, Center
from textual.widgets import Header, Footer, DataTable, Static, Button, Input, RadioSet, RadioButton, Label, LoadingIndicator
from textual.screen import Screen
from textual.binding import Binding
from textual import work


# ============================================================================
# Token 处理函数
# ============================================================================

def parse_datetime(date_str):
    """解析日期字符串为 datetime 对象"""
    try:
        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    except Exception:
        return None


def get_valid_tokens(tokens):
    """获取所有有效的 token（包含必需字段）"""
    valid_tokens = [
        t for t in tokens
        if all(key in t for key in ['accessToken', 'refreshToken', 'expiresAt'])
        and t.get('region') and t.get('clientId') and t.get('clientSecret')
    ]

    if not valid_tokens:
        raise ValueError("没有找到包含完整字段的有效 token")

    valid_tokens.sort(
        key=lambda t: parse_datetime(t['expiresAt']) or datetime.min,
        reverse=True
    )

    return valid_tokens


def detect_auth_type(token: Dict[str, Any]) -> str:
    """检测认证类型"""
    if token.get('clientId') and token.get('clientSecret'):
        return 'aws_sso_oidc'
    return 'kiro_desktop'


def refresh_token_kiro_desktop(token: Dict[str, Any]) -> Dict[str, Any]:
    """使用 Kiro Desktop Auth 刷新 token"""
    refresh_token = token.get('refreshToken')
    region = token.get('region', 'us-east-1')

    if not refresh_token:
        raise ValueError("缺少 refreshToken")

    url = f"https://prod.{region}.auth.desktop.kiro.dev/refreshToken"
    payload = {'refreshToken': refresh_token}
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "KiroIDE-0.7.45",
    }

    response = requests.post(url, json=payload, headers=headers, timeout=30)
    response.raise_for_status()
    data = response.json()

    new_access_token = data.get("accessToken")
    new_refresh_token = data.get("refreshToken")
    expires_in = data.get("expiresIn", 3600)

    if not new_access_token:
        raise ValueError(f"响应中没有 accessToken: {data}")

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in - 60)

    token['accessToken'] = new_access_token
    if new_refresh_token:
        token['refreshToken'] = new_refresh_token
    token['expiresAt'] = expires_at.isoformat()

    return token


def refresh_token_aws_sso_oidc(token: Dict[str, Any]) -> Dict[str, Any]:
    """使用 AWS SSO OIDC 刷新 token"""
    refresh_token = token.get('refreshToken')
    client_id = token.get('clientId')
    client_secret = token.get('clientSecret')
    region = token.get('region', 'us-east-1')

    if not refresh_token:
        raise ValueError("缺少 refreshToken")
    if not client_id:
        raise ValueError("缺少 clientId")
    if not client_secret:
        raise ValueError("缺少 clientSecret")

    url = f"https://oidc.{region}.amazonaws.com/token"
    payload = {
        "grantType": "refresh_token",
        "clientId": client_id,
        "clientSecret": client_secret,
        "refreshToken": refresh_token,
    }
    headers = {
        "Content-Type": "application/json",
    }

    response = requests.post(url, json=payload, headers=headers, timeout=30)
    response.raise_for_status()
    data = response.json()

    new_access_token = data.get("accessToken")
    new_refresh_token = data.get("refreshToken")
    expires_in = data.get("expiresIn", 3600)

    if not new_access_token:
        raise ValueError(f"响应中没有 accessToken: {data}")

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in - 60)

    token['accessToken'] = new_access_token
    if new_refresh_token:
        token['refreshToken'] = new_refresh_token
    token['expiresAt'] = expires_at.isoformat()

    return token


def generate_invocation_id() -> str:
    """生成 AWS SDK 调用 ID"""
    return str(uuid.uuid4())


def get_usage_limit(token: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """获取账户使用限额信息（使用 CBOR 格式）"""
    access_token = token.get('accessToken')

    if not access_token:
        return None

    url = 'https://app.kiro.dev/service/KiroWebPortalService/operation/GetUserUsageAndLimits'

    payload = {
        'isEmailRequired': True,
        'origin': 'KIRO_IDE'
    }

    headers = {
        'accept': 'application/cbor',
        'content-type': 'application/cbor',
        'smithy-protocol': 'rpc-v2-cbor',
        'amz-sdk-invocation-id': generate_invocation_id(),
        'amz-sdk-request': 'attempt=1; max=1',
        'x-amz-user-agent': 'aws-sdk-js/1.0.0 kiro-account-manager/1.0.0',
        'authorization': f'Bearer {access_token}',
        'cookie': f'Idp=BuilderId; AccessToken={access_token}'
    }

    try:
        cbor_body = cbor2.dumps(payload)
        response = requests.post(url, headers=headers, data=cbor_body, timeout=10)

        if response.status_code == 200:
            data = cbor2.loads(response.content)

            if '__type' in data:
                return None

            usage_breakdown = data.get('usageBreakdownList', [])
            credit_usage = next((item for item in usage_breakdown if item.get('resourceType') == 'CREDIT'), None)

            if credit_usage:
                base_limit = credit_usage.get('usageLimit', 0)
                base_used = credit_usage.get('currentUsage', 0)

                trial_limit = 0
                trial_used = 0
                if 'freeTrialInfo' in credit_usage:
                    trial_info = credit_usage['freeTrialInfo']
                    if trial_info.get('freeTrialStatus') == 'ACTIVE':
                        trial_limit = trial_info.get('usageLimit', 0)
                        trial_used = trial_info.get('currentUsage', 0)

                total_limit = base_limit + trial_limit
                total_used = base_used + trial_used
                total_remaining = total_limit - total_used

                return {
                    'limit': total_limit,
                    'used': total_used,
                    'remaining': total_remaining
                }

        return None

    except Exception:
        return None


def refresh_token(token: Dict[str, Any]) -> Dict[str, Any]:
    """刷新 token (自动检测认证类型)"""
    auth_type = detect_auth_type(token)

    if auth_type == 'aws_sso_oidc':
        token = refresh_token_aws_sso_oidc(token)
    else:
        token = refresh_token_kiro_desktop(token)

    usage_limit = get_usage_limit(token)
    if usage_limit:
        token['usageLimit'] = usage_limit

    return token


def convert_token(source_token):
    """将 tokens_export.json 中的 token 对象转换为 kiro-credentials.json 格式"""
    return {
        "accessToken": source_token["accessToken"],
        "refreshToken": source_token["refreshToken"],
        "expiresAt": source_token["expiresAt"],
        "region": source_token["region"],
        "clientId": source_token["clientId"],
        "clientSecret": source_token["clientSecret"]
    }


# ============================================================================
# 认证切换核心逻辑
# ============================================================================

class AuthSwitcher:
    """认证方式切换器"""

    def __init__(self, env_path: str = ".env"):
        self.env_path = Path(env_path)
        if not self.env_path.exists():
            raise FileNotFoundError(f"文件不存在: {env_path}")

    def read_env(self) -> list[str]:
        """读取 .env 文件"""
        with open(self.env_path, 'r', encoding='utf-8') as f:
            return f.readlines()

    def write_env(self, lines: list[str]) -> None:
        """写入 .env 文件"""
        with open(self.env_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)

    def get_current_auth(self) -> Tuple[str, str]:
        """获取当前启用的认证方式"""
        lines = self.read_env()

        for line in lines:
            stripped = line.strip()
            if stripped.startswith('#') or not stripped:
                continue

            if stripped.startswith('KIRO_CREDS_FILE='):
                value = stripped.split('=', 1)[1].strip('"\'')
                return ('creds-file', value)
            elif stripped.startswith('REFRESH_TOKEN='):
                value = stripped.split('=', 1)[1].strip('"\'')
                return ('refresh-token', value[:30] + '...' if len(value) > 30 else value)
            elif stripped.startswith('KIRO_CLI_DB_FILE='):
                value = stripped.split('=', 1)[1].strip('"\'')
                return ('cli-db', value)

        return ('none', '未配置')

    def switch_auth(self, method: str, value: str) -> None:
        """切换认证方式"""
        lines = self.read_env()
        new_lines = []
        current_section = None

        for line in lines:
            if "选项 1" in line or "OPTION 1" in line:
                current_section = "option1"
            elif "选项 2" in line or "OPTION 2" in line:
                current_section = "option2"
            elif "选项 3" in line or "OPTION 3" in line:
                current_section = "option3"
            elif "选项 4" in line or "OPTION 4" in line:
                current_section = "option4"
            elif line.startswith("# ==="):
                if "PROFILE ARN" in line or "可选" in line or "OPTIONAL" in line:
                    current_section = None

            if method == 'creds-file':
                if current_section == "option1" and "KIRO_CREDS_FILE" in line:
                    stripped = line.lstrip('#').strip()
                    if stripped.startswith("KIRO_CREDS_FILE"):
                        new_lines.append(f'KIRO_CREDS_FILE="{value}"\n')
                        continue
                elif current_section in ["option2", "option3", "option4"]:
                    if any(key in line for key in ["REFRESH_TOKEN", "KIRO_CLI_DB_FILE", "KIRO_CREDS_FILE"]):
                        stripped = line.strip()
                        if not stripped.startswith("#") and any(stripped.startswith(k) for k in ["REFRESH_TOKEN", "KIRO_CLI_DB_FILE", "KIRO_CREDS_FILE"]):
                            new_lines.append(f"# {line}")
                            continue

            elif method == 'refresh-token':
                if current_section == "option2" and "REFRESH_TOKEN" in line:
                    new_lines.append(f'REFRESH_TOKEN="{value}"\n')
                    continue
                elif current_section in ["option1", "option3", "option4"]:
                    if any(key in line for key in ["KIRO_CREDS_FILE", "KIRO_CLI_DB_FILE"]):
                        stripped = line.strip()
                        if not stripped.startswith("#") and any(stripped.startswith(k) for k in ["KIRO_CREDS_FILE", "KIRO_CLI_DB_FILE"]):
                            new_lines.append(f"# {line}")
                            continue

            elif method == 'cli-db':
                if current_section == "option3" and "KIRO_CLI_DB_FILE" in line:
                    stripped = line.lstrip('#').strip()
                    if stripped.startswith("KIRO_CLI_DB_FILE"):
                        new_lines.append(f'KIRO_CLI_DB_FILE="{value}"\n')
                        continue
                elif current_section in ["option1", "option2", "option4"]:
                    if any(key in line for key in ["KIRO_CREDS_FILE", "REFRESH_TOKEN"]):
                        stripped = line.strip()
                        if not stripped.startswith("#") and any(stripped.startswith(k) for k in ["KIRO_CREDS_FILE", "REFRESH_TOKEN"]):
                            new_lines.append(f"# {line}")
                            continue

            new_lines.append(line)

        self.write_env(new_lines)




# ============================================================================
# TUI 界面组件
# ============================================================================

class LoadingScreen(Screen):
    """加载进度屏幕"""

    def __init__(self, message: str = "处理中...", **kwargs):
        super().__init__(**kwargs)
        self.message = message

    def compose(self) -> ComposeResult:
        with Container(id="loading-dialog"):
            yield Static("请稍候", id="loading-title")
            yield LoadingIndicator(id="loading-spinner")
            yield Static(self.message, id="loading-message")

    def update_message(self, message: str) -> None:
        """更新加载消息"""
        self.query_one("#loading-message", Static).update(message)


class StatusScreen(Screen):
    """状态显示屏幕"""

    BINDINGS = [
        Binding("enter", "close", "关闭", priority=True),
        Binding("escape", "close", "关闭", show=False),
    ]

    def __init__(self, title: str, message: str, is_error: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.title = title
        self.message = message
        self.is_error = is_error

    def compose(self) -> ComposeResult:
        with Container(id="status-dialog"):
            yield Static(self.title, id="status-title")
            yield Static(self.message, id="status-message", classes="error" if self.is_error else "success")
            yield Button("关闭 (Enter)", variant="primary", id="btn-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss()

    def action_close(self) -> None:
        self.dismiss()


class ConfirmScreen(Screen):
    """确认对话框"""

    BINDINGS = [
        Binding("y", "confirm", "确认 (Y)", priority=True),
        Binding("n", "cancel", "取消 (N)", priority=True),
        Binding("escape", "cancel", "取消", show=False),
    ]

    def __init__(self, message: str, **kwargs):
        super().__init__(**kwargs)
        self.message = message

    def compose(self) -> ComposeResult:
        with Container(id="confirm-dialog"):
            yield Static(self.message, id="confirm-message")
            with Horizontal(id="confirm-buttons"):
                yield Button("确认 (Y)", variant="success", id="btn-yes")
                yield Button("取消 (N)", variant="error", id="btn-no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-yes":
            self.dismiss(True)
        else:
            self.dismiss(False)

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class MainMenuScreen(Screen):
    """主菜单屏幕"""

    BINDINGS = [
        Binding("1", "token_converter", "Token 转换", priority=True),
        Binding("2", "auth_switcher", "认证切换", priority=True),
        Binding("q", "quit", "退出", priority=True),
    ]

    def compose(self) -> ComposeResult:
        with Center():
            with Container(id="main-menu"):
                yield Static("Kiro Gateway 工具集", id="menu-title")
                yield Static("", id="menu-subtitle")
                with Container(id="menu-buttons"):
                    yield Button("[1] Token 转换工具", variant="primary", id="btn-token-converter")
                    yield Button("[2] 认证切换工具", variant="primary", id="btn-auth-switcher")
                    yield Button("[Q] 退出", variant="error", id="btn-quit")
                yield Static("提示: 使用数字键或点击按钮选择功能", id="menu-hint")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-token-converter":
            self.action_token_converter()
        elif event.button.id == "btn-auth-switcher":
            self.action_auth_switcher()
        elif event.button.id == "btn-quit":
            self.app.exit()

    def on_key(self, event) -> None:
        """处理键盘事件"""
        if event.key == "1":
            self.action_token_converter()
        elif event.key == "2":
            self.action_auth_switcher()
        elif event.key == "q" or event.key == "Q":
            self.app.exit()

    def action_token_converter(self) -> None:
        self.app.push_screen("token_converter")

    def action_auth_switcher(self) -> None:
        self.app.push_screen("auth_switcher")

    def action_quit(self) -> None:
        self.app.exit()


class TokenConverterScreen(Screen):
    """Token 转换工具屏幕"""

    BINDINGS = [
        Binding("escape", "back", "返回", priority=True),
        Binding("r", "refresh_token", "刷新 Token", priority=True),
        Binding("c", "convert", "转换并保存", priority=True),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.tokens: List[Dict[str, Any]] = []
        self.all_tokens: List[Dict[str, Any]] = []
        self.selected_token: Optional[Dict[str, Any]] = None
        self.source_file = Path(__file__).parent / "tokens_export.json"
        self.target_file = Path(__file__).parent / "kiro-credentials.json"
        self.current_credentials: Optional[Dict[str, Any]] = None
        self.last_click_time = 0
        self.last_click_row = None

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="main-container"):
            yield Static("Token 转换工具", id="title")
            yield Static(f"源文件: {self.source_file.name} → 目标文件: {self.target_file.name}", id="info")
            yield Static("提示: 双击表格行可快速刷新 Token", id="hint", classes="hint-text")
            yield DataTable(id="token-table")
            yield Static("", id="token-details")
            with Horizontal(id="actions"):
                yield Button("刷新 Token (R)", variant="primary", id="btn-refresh")
                yield Button("转换并保存 (C)", variant="success", id="btn-convert")
                yield Button("返回 (ESC)", variant="default", id="btn-back")
        yield Footer()

    def on_mount(self) -> None:
        try:
            self.load_current_credentials()
            self.load_tokens()
            self.setup_table()
        except Exception as e:
            self.app.push_screen(StatusScreen("错误", f"加载失败: {e}", is_error=True))
            self.action_back()

    def load_current_credentials(self) -> None:
        """加载当前使用的凭证"""
        try:
            if self.target_file.exists():
                with open(self.target_file, 'r', encoding='utf-8') as f:
                    self.current_credentials = json.load(f)
        except Exception:
            self.current_credentials = None

    def load_tokens(self) -> None:
        with open(self.source_file, 'r', encoding='utf-8') as f:
            self.all_tokens = json.load(f)
        self.tokens = get_valid_tokens(self.all_tokens)
        if self.tokens:
            self.selected_token = self.tokens[0]

    def setup_table(self) -> None:
        table = self.query_one("#token-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("序号", "状态", "邮箱", "过期时间", "区域", "订阅类型", "")

        now = datetime.now(datetime.now().astimezone().tzinfo)
        current_refresh_token = self.current_credentials.get('refreshToken') if self.current_credentials else None

        for idx, token in enumerate(self.tokens, 1):
            expires_at = parse_datetime(token['expiresAt'])
            is_expired = expires_at < now if expires_at else True
            status = "[过期]" if is_expired else "[有效]"

            # 通过refreshToken匹配当前使用的token
            is_current = token.get('refreshToken') == current_refresh_token if current_refresh_token else False
            marker = "当前使用" if is_current else ""

            table.add_row(
                str(idx),
                status,
                token.get('email', 'N/A')[:30],
                token['expiresAt'][:19],
                token['region'],
                token.get('subscriptionTitle', 'N/A')[:20],
                marker,
                key=str(idx)
            )

    def refresh_table(self) -> None:
        """刷新表格显示"""
        table = self.query_one("#token-table", DataTable)

        # 保存当前选中的token的clientId
        selected_client_id = self.selected_token.get('clientId') if self.selected_token else None

        # 清空表格
        table.clear()

        # 重新加载tokens和当前凭证
        self.load_tokens()
        self.load_current_credentials()

        # 重新填充表格
        now = datetime.now(datetime.now().astimezone().tzinfo)
        selected_row_key = None
        current_refresh_token = self.current_credentials.get('refreshToken') if self.current_credentials else None

        for idx, token in enumerate(self.tokens, 1):
            expires_at = parse_datetime(token['expiresAt'])
            is_expired = expires_at < now if expires_at else True
            status = "[过期]" if is_expired else "[有效]"

            # 通过refreshToken匹配当前使用的token
            is_current = token.get('refreshToken') == current_refresh_token if current_refresh_token else False
            marker = "当前使用" if is_current else ""

            table.add_row(
                str(idx),
                status,
                token.get('email', 'N/A')[:30],
                token['expiresAt'][:19],
                token['region'],
                token.get('subscriptionTitle', 'N/A')[:20],
                marker,
                key=str(idx)
            )

            # 找到之前选中的token
            if selected_client_id and token.get('clientId') == selected_client_id:
                selected_row_key = str(idx)
                self.selected_token = token

        # 恢复选中状态
        if selected_row_key:
            table.move_cursor(row=int(selected_row_key) - 1)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        row_key = event.row_key.value
        idx = int(row_key) - 1

        # 检测双击
        current_time = time.time()
        is_double_click = (
            self.last_click_row == row_key and
            (current_time - self.last_click_time) < 0.5
        )

        # 更新选中的token
        self.selected_token = self.tokens[idx]
        self.update_details()

        # 如果是双击，触发刷新
        if is_double_click:
            self.action_refresh_token()
            # 重置双击状态
            self.last_click_time = 0
            self.last_click_row = None
        else:
            # 记录本次点击
            self.last_click_time = current_time
            self.last_click_row = row_key

    def update_details(self) -> None:
        if not self.selected_token:
            return

        token = self.selected_token
        expires_at = parse_datetime(token['expiresAt'])
        now = datetime.now(datetime.now().astimezone().tzinfo)
        is_expired = expires_at < now if expires_at else True

        details = f"""[b]选中的 Token 详情:[/b]

邮箱: {token.get('email', 'N/A')}
过期时间: {token['expiresAt']}
区域: {token['region']}
订阅类型: {token.get('subscriptionTitle', 'N/A')}
Client ID: {token['clientId'][:40]}...
状态: {'已过期' if is_expired else '有效'}
"""

        if 'usageLimit' in token:
            usage = token['usageLimit']
            details += f"\n使用限额: {usage['used']}/{usage['limit']} (剩余: {usage['remaining']})"

        self.query_one("#token-details", Static).update(details)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-refresh":
            self.action_refresh_token()
        elif event.button.id == "btn-convert":
            self.action_convert()
        elif event.button.id == "btn-back":
            self.action_back()

    def action_refresh_token(self) -> None:
        if not self.selected_token:
            return

        def handle_confirm(confirmed: bool) -> None:
            if confirmed:
                self.refresh_selected_token()

        self.app.push_screen(
            ConfirmScreen("确定要刷新选中的 Token 吗？\n这将更新 accessToken 和 expiresAt"),
            handle_confirm
        )

    def refresh_selected_token(self) -> None:
        """刷新选中的token（带进度指示）"""
        loading_screen = LoadingScreen("正在刷新 Token...")
        self.app.push_screen(loading_screen)

        # 启动后台任务
        self._do_refresh_token(loading_screen)

    @work(exclusive=True, thread=True)
    def _do_refresh_token(self, loading_screen: LoadingScreen) -> None:
        """执行token刷新的后台任务"""
        try:
            # 步骤1: 检测认证类型
            self.app.call_from_thread(loading_screen.update_message, "正在检测认证类型...")
            auth_type = detect_auth_type(self.selected_token)

            # 步骤2: 刷新token
            self.app.call_from_thread(loading_screen.update_message, f"正在刷新 Token ({auth_type})...")
            self.selected_token = refresh_token(self.selected_token)

            # 步骤3: 更新本地数据
            self.app.call_from_thread(loading_screen.update_message, "正在更新本地数据...")
            for i, token in enumerate(self.all_tokens):
                if token.get('clientId') == self.selected_token.get('clientId'):
                    self.all_tokens[i]['expiresAt'] = self.selected_token['expiresAt']
                    self.all_tokens[i]['accessToken'] = self.selected_token['accessToken']
                    self.all_tokens[i]['refreshToken'] = self.selected_token['refreshToken']

                    if 'usageLimit' in self.selected_token:
                        self.all_tokens[i]['usageLimit'] = self.selected_token['usageLimit']

                    self.all_tokens[i]['lastRefreshed'] = datetime.now(timezone.utc).isoformat()
                    break

            # 步骤4: 保存到文件
            self.app.call_from_thread(loading_screen.update_message, "正在保存到文件...")
            with open(self.source_file, 'w', encoding='utf-8') as f:
                json.dump(self.all_tokens, f, indent=2, ensure_ascii=False)

            # 步骤5: 更新界面
            self.app.call_from_thread(loading_screen.update_message, "正在更新界面...")
            self.app.call_from_thread(self.refresh_table)
            self.app.call_from_thread(self.update_details)

            # 关闭加载屏幕
            self.app.call_from_thread(self.app.pop_screen)

            # 显示成功消息
            message = f"""Token 刷新成功

过期时间: {self.selected_token['expiresAt']}
Access Token: {self.selected_token['accessToken'][:30]}...
"""
            if 'usageLimit' in self.selected_token:
                usage = self.selected_token['usageLimit']
                message += f"\n使用限额: {usage['used']}/{usage['limit']} (剩余: {usage['remaining']})"

            self.app.call_from_thread(self.app.push_screen, StatusScreen("刷新成功", message))

        except Exception as e:
            # 关闭加载屏幕
            self.app.call_from_thread(self.app.pop_screen)
            # 显示错误消息
            self.app.call_from_thread(self.app.push_screen, StatusScreen("刷新失败", f"错误: {e}", is_error=True))

    def action_convert(self) -> None:
        if not self.selected_token:
            return

        def handle_confirm(confirmed: bool) -> None:
            if confirmed:
                self.convert_and_save()

        self.app.push_screen(
            ConfirmScreen(f"确定要将选中的 Token 转换并保存到\n{self.target_file.name} 吗？"),
            handle_confirm
        )

    def convert_and_save(self) -> None:
        try:
            credentials = convert_token(self.selected_token)

            with open(self.target_file, 'w', encoding='utf-8') as f:
                json.dump(credentials, f, indent=2, ensure_ascii=False)

            # 更新当前凭证显示
            self.load_current_credentials()
            self.refresh_table()

            message = f"""转换完成

已保存到: {self.target_file}

邮箱: {self.selected_token.get('email', 'N/A')}
区域: {self.selected_token['region']}
过期时间: {self.selected_token['expiresAt']}
"""

            self.app.push_screen(StatusScreen("转换成功", message))

        except Exception as e:
            self.app.push_screen(StatusScreen("转换失败", f"错误: {e}", is_error=True))

    def action_back(self) -> None:
        self.app.pop_screen()



class AuthSwitcherScreen(Screen):
    """认证切换工具屏幕"""

    BINDINGS = [
        Binding("escape", "back", "返回", priority=True),
        Binding("s", "switch", "切换认证", priority=True),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.switcher: Optional[AuthSwitcher] = None
        self.env_path = Path(__file__).parent / ".env"
        self.selected_method: str = "creds-file"
        self.default_values = {
            "creds-file": "./kiro-credentials.json",
            "refresh-token": "",
            "cli-db": "~/.local/share/kiro-cli/data.sqlite3"
        }

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="main-container"):
            yield Static("认证方式切换工具", id="title")

            with Container(id="current-auth"):
                yield Static("当前认证方式", id="current-auth-title")
                yield Static("", id="current-auth-info")

            with Container(id="auth-selection"):
                yield Static("选择新的认证方式", id="auth-selection-title")
                with RadioSet(id="auth-radio"):
                    yield RadioButton("[1] KIRO_CREDS_FILE - Kiro IDE 凭证文件", value=True, id="radio-creds-file")
                    yield RadioButton("[2] REFRESH_TOKEN - 刷新令牌", id="radio-refresh-token")
                    yield RadioButton("[3] KIRO_CLI_DB_FILE - kiro-cli SQLite 数据库", id="radio-cli-db")

            with Container(id="input-container"):
                yield Label("配置值", id="input-label")
                yield Input(placeholder="请输入配置值...", id="value-input")
                yield Static("", id="input-hint")

            with Horizontal(id="actions"):
                yield Button("切换认证 (S)", variant="success", id="btn-switch")
                yield Button("返回 (ESC)", variant="default", id="btn-back")

            yield Static("提示: 切换后其他认证方式将自动注释，需重启服务生效", id="help-text")

        yield Footer()

    def on_mount(self) -> None:
        try:
            self.switcher = AuthSwitcher(str(self.env_path))
            self.update_current_auth()
            self.update_input_hint()

            input_widget = self.query_one("#value-input", Input)
            input_widget.value = self.default_values["creds-file"]

        except Exception as e:
            self.app.push_screen(StatusScreen("错误", f"初始化失败: {e}", is_error=True))
            self.action_back()

    def update_current_auth(self) -> None:
        if not self.switcher:
            return

        method, value = self.switcher.get_current_auth()

        method_names = {
            'creds-file': 'KIRO_CREDS_FILE (凭证文件)',
            'refresh-token': 'REFRESH_TOKEN (刷新令牌)',
            'cli-db': 'KIRO_CLI_DB_FILE (CLI 数据库)',
            'none': '未配置'
        }

        info = f"{method_names.get(method, '未知')}\n"
        if method != 'none':
            info += f"值: {value}"

        self.query_one("#current-auth-info", Static).update(info)

    def update_input_hint(self) -> None:
        hints = {
            "creds-file": "示例: ./kiro-credentials.json",
            "refresh-token": "示例: eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
            "cli-db": "示例: ~/.local/share/kiro-cli/data.sqlite3"
        }

        hint = hints.get(self.selected_method, "")
        self.query_one("#input-hint", Static).update(f"提示: {hint}")

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        radio_id = event.pressed.id

        method_map = {
            "radio-creds-file": "creds-file",
            "radio-refresh-token": "refresh-token",
            "radio-cli-db": "cli-db"
        }

        self.selected_method = method_map.get(radio_id, "creds-file")
        self.update_input_hint()

        input_widget = self.query_one("#value-input", Input)
        input_widget.value = self.default_values[self.selected_method]

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-switch":
            self.action_switch()
        elif event.button.id == "btn-back":
            self.action_back()

    def action_switch(self) -> None:
        input_widget = self.query_one("#value-input", Input)
        value = input_widget.value.strip()

        if not value:
            self.app.push_screen(StatusScreen("错误", "配置值不能为空", is_error=True))
            return

        method_names = {
            "creds-file": "KIRO_CREDS_FILE",
            "refresh-token": "REFRESH_TOKEN",
            "cli-db": "KIRO_CLI_DB_FILE"
        }

        try:
            self.switcher.switch_auth(self.selected_method, value)
            self.update_current_auth()

            message = f"""切换成功

认证方式: {method_names[self.selected_method]}
配置值: {value[:50]}{'...' if len(value) > 50 else ''}

提示:
  - 其他认证方式已自动注释
  - 请重启服务以应用新配置
"""

            self.app.push_screen(StatusScreen("切换成功", message))

        except Exception as e:
            self.app.push_screen(StatusScreen("切换失败", f"错误: {e}", is_error=True))

    def action_back(self) -> None:
        self.app.pop_screen()


class KiroToolsApp(App):
    """Kiro Gateway 工具集主应用"""

    CSS = """
    Screen {
        background: black;
    }

    * {
        color: white;
        background: black;
    }

    #main-menu {
        width: 40;
        height: auto;
        padding: 0;
        background: black;
        border: solid white;
    }

    #menu-title {
        text-align: center;
        color: white;
        background: black;
    }

    #menu-buttons Button {
        width: 100%;
        margin: 0;
        color: white;
        background: black;
        border: solid white;
    }

    #menu-buttons Button:hover {
        background: #333333;
        color: #aaaaaa;
    }

    #menu-buttons Button:focus {
        background: #555555;
        color: #ffff00;
        border: solid #ffff00;
        text-style: bold;
    }

    #menu-hint {
        text-align: center;
        color: #888888;
        background: black;
    }

    #main-container {
        width: 100%;
        height: 100%;
        padding: 0;
        background: black;
    }

    #title {
        text-align: center;
        color: white;
        background: black;
    }

    #info {
        text-align: center;
        color: #888888;
        background: black;
    }

    .hint-text {
        text-align: center;
        color: #00ff00;
        background: black;
        text-style: italic;
        padding: 0 0 1 0;
    }

    .current-token {
        text-align: center;
        color: #00ffff;
        background: #1a1a1a;
        text-style: bold;
        padding: 1;
        border: solid #00ffff;
    }

    DataTable {
        height: 1fr;
        background: black;
        color: white;
        border: solid white;
    }

    DataTable > .datatable--cursor {
        background: #555555;
        color: #ffff00;
        text-style: bold;
    }

    DataTable > .datatable--hover {
        background: #333333;
    }

    DataTable:focus > .datatable--cursor {
        background: #777777;
        color: #ffff00;
        text-style: bold;
    }

    DataTable > .datatable--header {
        background: #222222;
        color: white;
        text-style: bold;
    }

    #token-details {
        height: auto;
        padding: 0;
        background: black;
        color: white;
    }

    #current-auth {
        height: auto;
        padding: 0;
        background: black;
        color: white;
    }

    #auth-selection {
        height: auto;
        padding: 0;
        background: black;
    }

    RadioSet {
        height: auto;
        background: black;
    }

    RadioButton {
        margin: 0;
        color: white;
        background: black;
        padding: 1;
    }

    RadioButton:hover {
        background: #333333;
        color: #aaaaaa;
    }

    RadioButton:focus {
        background: #444444;
        color: white;
        border: solid #888888;
    }

    RadioButton.-selected {
        background: #555555;
        color: #ffff00;
        text-style: bold;
        border: solid #ffff00;
    }

    RadioButton.-selected:focus {
        background: #666666;
        color: #ffff00;
        text-style: bold;
        border: solid #ffff00;
    }

    #input-container {
        height: auto;
        padding: 0;
        background: black;
    }

    Input {
        margin: 0;
        color: white;
        background: black;
        border: solid white;
    }

    Input:focus {
        border: solid white;
    }

    #actions {
        height: auto;
        background: black;
    }

    #actions Button {
        margin: 0 1;
        color: white;
        background: black;
        border: solid white;
    }

    #actions Button:hover {
        background: #333333;
        color: #aaaaaa;
    }

    #actions Button:focus {
        background: #555555;
        color: #ffff00;
        border: solid #ffff00;
        text-style: bold;
    }

    #status-dialog, #confirm-dialog, #loading-dialog {
        width: 50;
        height: auto;
        padding: 1;
        background: black;
        border: solid white;
    }

    #loading-dialog {
        align: center middle;
    }

    #loading-title {
        text-align: center;
        color: white;
        background: black;
        padding: 0 0 1 0;
    }

    #loading-spinner {
        width: 100%;
        height: 3;
        content-align: center middle;
        background: black;
    }

    #loading-message {
        text-align: center;
        color: #888888;
        background: black;
        padding: 1 0 0 0;
    }

    #status-message {
        padding: 0;
        color: white;
        background: black;
    }

    #confirm-buttons {
        height: auto;
        background: black;
    }

    #confirm-buttons Button {
        margin: 0 1;
        color: white;
        background: black;
        border: solid white;
    }

    #confirm-buttons Button:hover {
        background: #333333;
        color: #aaaaaa;
    }

    #confirm-buttons Button:focus {
        background: #555555;
        color: #ffff00;
        border: solid #ffff00;
        text-style: bold;
    }

    #help-text {
        text-align: center;
        color: #888888;
        background: black;
    }
    """

    SCREENS = {
        "main_menu": MainMenuScreen,
        "token_converter": TokenConverterScreen,
        "auth_switcher": AuthSwitcherScreen,
    }

    def on_mount(self) -> None:
        self.push_screen("main_menu")


def main():
    """主函数"""
    app = KiroToolsApp()
    app.run()


if __name__ == "__main__":
    main()
