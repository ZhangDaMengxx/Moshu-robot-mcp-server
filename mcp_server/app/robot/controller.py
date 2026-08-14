"""机器人控制器 - 调用硬件代理。"""
import asyncio
from datetime import datetime, timezone
import logging
from typing import Optional

import httpx


logger = logging.getLogger(__name__)


class RobotController:
    def __init__(self, bridge_url: str, bridge_token: str = "",
                 heartbeat_interval: float = 5.0,
                 heartbeat_timeout: float = 2.0,
                 client: Optional[httpx.AsyncClient] = None):
        self.bridge_url = bridge_url
        self.bridge_token = bridge_token
        self.heartbeat_interval = heartbeat_interval
        self.heartbeat_timeout = heartbeat_timeout
        self.client = client
        self._connected = False
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._consecutive_failures = 0
        self._last_seen: Optional[datetime] = None
        self._last_error: Optional[str] = None

    async def connect(self) -> bool:
        """启动时连接；失败不阻止 MCP Server 启动。"""
        if self.client is None or self.client.is_closed:
            headers = {}
            if self.bridge_token:
                headers["X-Bridge-Token"] = self.bridge_token
            self.client = httpx.AsyncClient(
                base_url=self.bridge_url,
                timeout=10.0,
                headers=headers,
            )

        if await self.check_health():
            logger.info("✓ 硬件代理已连接: %s", self.bridge_url)
            return True

        logger.warning("硬件代理连接失败，服务将以降级模式运行")
        return False

    def _mark_success(self) -> None:
        was_disconnected = not self._connected
        previous_failures = self._consecutive_failures
        self._connected = True
        self._consecutive_failures = 0
        self._last_seen = datetime.now(timezone.utc)
        self._last_error = None
        if was_disconnected and previous_failures:
            logger.info("✓ 硬件代理连接已恢复: %s", self.bridge_url)

    def _mark_failure(self, error: Exception | str) -> None:
        was_connected = self._connected
        self._connected = False
        self._consecutive_failures += 1
        if isinstance(error, Exception):
            self._last_error = f"{type(error).__name__}: {error}"
        else:
            self._last_error = error
        if was_connected or self._consecutive_failures == 1:
            logger.warning("硬件代理连接中断: %s", self._last_error)
        else:
            logger.debug("硬件代理仍不可用(%d 次): %s",
                         self._consecutive_failures, self._last_error)

    async def check_health(self) -> bool:
        """探测 Bridge；失败只更新状态，不向后台任务抛异常。"""
        if self.client is None or self.client.is_closed:
            self._mark_failure("HTTP client not initialized")
            return False
        try:
            resp = await self.client.get("/health", timeout=self.heartbeat_timeout)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            self._mark_failure(e)
            return False
        self._mark_success()
        return True

    def start_heartbeat(self) -> None:
        """启动后台心跳；重复调用不会创建多个任务。"""
        if self._heartbeat_task and not self._heartbeat_task.done():
            return
        self._heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(), name="robot-bridge-heartbeat")
        logger.info("Bridge 心跳已启动: interval=%.1fs timeout=%.1fs",
                    self.heartbeat_interval, self.heartbeat_timeout)

    async def _heartbeat_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self.heartbeat_interval)
                await self.check_health()
        except asyncio.CancelledError:
            raise

    async def stop_heartbeat(self) -> None:
        task = self._heartbeat_task
        self._heartbeat_task = None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        logger.info("Bridge 心跳已停止")

    def connection_status(self) -> dict:
        """返回可序列化的连接状态，供 MCP 健康检查和运维查看。"""
        return {
            "connected": self._connected,
            "heartbeat_interval_seconds": self.heartbeat_interval,
            "consecutive_failures": self._consecutive_failures,
            "last_seen": self._last_seen.isoformat() if self._last_seen else None,
            "last_error": self._last_error,
        }

    async def ensure_connected(self) -> None:
        """确保连接可用（懒加载 + 重连）。"""
        if self._connected:
            return

        if self.client is None or self.client.is_closed:
            await self.connect()
        else:
            await self.check_health()

        if not self._connected:
            raise RuntimeError(
                f"硬件代理不可用: {self._last_error or 'unknown error'}")

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """执行一次 Bridge 请求；运动命令不会在这里被自动重试。"""
        await self.ensure_connected()
        assert self.client is not None
        try:
            resp = await self.client.request(method, path, **kwargs)
        except httpx.RequestError as e:
            self._mark_failure(e)
            raise RuntimeError(f"硬件代理请求失败: {e}") from e
        self._mark_success()
        return resp

    async def disconnect(self) -> None:
        """停止心跳并关闭 HTTP 客户端。"""
        await self.stop_heartbeat()
        if self.client:
            await self.client.aclose()
            self.client = None
            self._connected = False
            logger.info("硬件代理已断开")

    # ========================================================================
    # 灵巧手
    # ========================================================================
    async def hand_status(self):
        """查询手状态。"""
        resp = await self._request("GET", "/hand/status")
        resp.raise_for_status()
        return resp.json()

    async def hand_set_angles(self, angles: list[float]):
        """设置手关节角度。不可行姿态 bridge 回 409，原因原样透出。

        不转发 allow_infeasible：放行开关只给本机标定脚本，不给远端调用方。
        """
        resp = await self._request("POST", "/hand/angles", json={"angles": angles})
        if resp.status_code in (400, 409):
            raise ValueError(resp.json().get("detail", resp.text))
        resp.raise_for_status()
        return resp.json()

    async def hand_gesture(self, name: str):
        """执行手势，不可行姿态的原因原样透出。"""
        resp = await self._request("POST", f"/hand/gesture/{name}")
        if resp.status_code in (400, 404, 409):
            detail = resp.json().get("detail", resp.text)
            raise ValueError(detail)
        resp.raise_for_status()
        return resp.json()

    async def hand_list_gestures(self):
        """列出可用手势。"""
        resp = await self._request("GET", "/hand/gestures")
        resp.raise_for_status()
        return resp.json()

    # ========================================================================
    # 机械臂
    # ========================================================================
    async def arm_status(self):
        """查询臂状态。"""
        resp = await self._request("GET", "/arm/status")
        resp.raise_for_status()
        return resp.json()

    async def arm_set_joints(self, joints: list[float]):
        """设置臂关节角度。"""
        resp = await self._request("POST", "/arm/joints", json={"joints": joints})
        resp.raise_for_status()
        return resp.json()

    async def arm_enable(self):
        """使能机械臂电机。"""
        resp = await self._request("POST", "/arm/enable")
        resp.raise_for_status()
        return resp.json()

    async def arm_disable(self):
        """下使能机械臂电机。"""
        resp = await self._request("POST", "/arm/disable")
        resp.raise_for_status()
        return resp.json()

    async def arm_estop(self):
        """机械臂急停。"""
        resp = await self._request("POST", "/arm/estop")
        resp.raise_for_status()
        return resp.json()

    async def arm_reset(self):
        """退出急停并重新使能。"""
        resp = await self._request("POST", "/arm/reset")
        resp.raise_for_status()
        return resp.json()
