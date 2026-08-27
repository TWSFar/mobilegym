#!/bin/bash
# ===========================================================================
# 批量拉起 N 个 MobileGym "device" 并注册到 UIAgent 网关（宿主机进程，无 Docker）。
#
# 对齐 mua-gateway/scripts/start_mobile_containers.sh 的写法：
#   signature   : <device_count> <gateway_url>，都带默认值
#   gateway_url : 完整 URL，脚本自动补 /heartbeat
#   端口分配    : adapter 从 BASE_PORT(默认 8100) 顺序递增 8100,8101,...
#   心跳        : 脚本末尾起一个宿主机后台循环，逐端口 POST /heartbeat
#
# MobileGym 的一个 device = 前端静态站点(nginx dist/) + 一个 adapter
# (bench_env/server/env_server.py，Playwright 浏览器 + 网关 HTTP 协议)。
# 前端是无状态静态站点，N 个 adapter 共用同一个前端（每个 adapter 各开自己的
# 浏览器实例，互不干扰），所以整台机器只起 1 个前端。
#
# 用法（在 mobilegym 仓库根目录执行）：
#   bash bench_env/server/start_gateway_device.sh                 # 8 个，默认网关
#   bash bench_env/server/start_gateway_device.sh 16 http://net.host/path/
#
# 可选环境变量：
#   BASE_PORT      adapter 起始端口（默认 8100）
#   FRONTEND_PORT  前端 nginx 端口（默认 4180，仅本机访问）
#   PYTHON_BIN     python 可执行文件（默认 python）
# ===========================================================================
set -uo pipefail

# --- 参数（对齐 mobile_world：device_count 默认 8，gateway_url 带默认值）---
DEVICE_COUNT=${1:-8}
GATEWAY_URL=${2:-http://webui.train.ai.srv/d1v7-04-101/}
GATEWAY_URL="${GATEWAY_URL%/}/heartbeat"

BASE_PORT=${BASE_PORT:-8100}
FRONTEND_PORT=${FRONTEND_PORT:-4180}
PYTHON_BIN="${PYTHON_BIN:-python}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT_DIR" || exit 1

# adapter 用 HTTPS 连自签名前端；MobileGymEnv 以 --ignore-certificate-errors 启动。
MOBILEGYM_ENV_URL="https://127.0.0.1:${FRONTEND_PORT}"

HOST_IP=$(hostname -I | awk '{print $1}')
if [ -z "$HOST_IP" ]; then
  HOST_IP="127.0.0.1"
fi

echo "=================================================="
echo "device_count : $DEVICE_COUNT"
echo "gateway      : $GATEWAY_URL"
echo "adapter 端口 : ${BASE_PORT}..$((BASE_PORT + DEVICE_COUNT - 1))  (宿主机IP=$HOST_IP)"
echo "前端 nginx   : :$FRONTEND_PORT (dist/，仅本机)"
echo "=================================================="

# --- 0. 依赖检查（挂载源码/裸环境时确保 adapter 依赖存在）---
if ! "$PYTHON_BIN" -c "import fastapi, uvicorn, pydantic" >/dev/null 2>&1; then
  echo ">>> 安装 python 依赖 (fastapi/uvicorn/pydantic + bench_env)..."
  "$PYTHON_BIN" -m pip install --no-cache-dir -q \
    -r bench_env/requirements.txt fastapi "uvicorn[standard]" pydantic || {
      echo "ERROR: python 依赖安装失败" >&2; exit 1; }
fi

if [ ! -d "$ROOT_DIR/dist" ]; then
  echo "ERROR: dist/ 不存在，请先在仓库根目录执行 npm run build 构建前端。" >&2
  exit 1
fi

# --- 0.5 清理上一轮遗留进程（幂等重启：无需手动 kill）---
# 只清理本脚本会启动的三类进程，且 adapter 仅限本次的端口段，避免误杀他人进程：
#   - adapter : python -m bench_env.server.env_server --port <BASE_PORT..BASE_PORT+N-1>
#   - 心跳    : 带 MOBILEGYM_HEARTBEAT 标记的 bash 循环
#   - nginx   : 由 start_nginx_gateway.sh stop 统一停（下面起 nginx 时它自己也会 stop 旧实例）
cleanup_stale() {
  echo ">>> 清理上一轮遗留进程 ..."

  # 1) 心跳守护进程（精确匹配标记，避免误杀）
  pkill -f "MOBILEGYM_HEARTBEAT" 2>/dev/null && echo "    已停止旧心跳进程"

  # 2) 本次端口段内的 adapter
  local port pids
  for ((i=1; i<=DEVICE_COUNT; i++)); do
    port=$((BASE_PORT + i - 1))
    # 精确匹配 env_server 且端口号完全一致（\b 防止 810 误匹配 8100）
    pids=$(pgrep -f "bench_env\.server\.env_server.*--port ${port}\b" 2>/dev/null)
    if [ -n "$pids" ]; then
      echo "    终止端口 $port 的旧 adapter (PID: $pids)"
      kill $pids 2>/dev/null
    fi
  done

  # 3) 给端口一点时间释放，必要时强杀仍未退出的
  sleep 1
  for ((i=1; i<=DEVICE_COUNT; i++)); do
    port=$((BASE_PORT + i - 1))
    pids=$(pgrep -f "bench_env\.server\.env_server.*--port ${port}\b" 2>/dev/null)
    if [ -n "$pids" ]; then
      echo "    强制终止端口 $port 的残留 adapter (PID: $pids)"
      kill -9 $pids 2>/dev/null
    fi
  done
}
cleanup_stale

# --- 1. 起前端 nginx（整台机器只起 1 个，N 个 adapter 共用）---
echo ">>> 启动前端 nginx :$FRONTEND_PORT ..."
bash scripts/server/start_nginx_gateway.sh "$FRONTEND_PORT"

# 等前端应答后再拉 adapter（避免 Playwright 打开时前端还没起来）。
echo -n ">>> 等待前端就绪 "
for _ in $(seq 1 60); do
  if curl -sk "https://127.0.0.1:${FRONTEND_PORT}/" >/dev/null 2>&1; then
    echo "OK"; break
  fi
  echo -n "."; sleep 1
done

# --- 2. 顺序拉起 N 个 adapter ---
ADAPTER_PIDS=()
DECLARED_PORTS=()

for ((i=1; i<=DEVICE_COUNT; i++)); do
  PORT=$((BASE_PORT + i - 1))

  if ss -lnt | grep -q ":$PORT "; then
    echo "警告: 端口 $PORT 已被占用，跳过（请释放端口或调整 BASE_PORT）"
    continue
  fi

  echo "--------------------------------------------------"
  echo "[$i/$DEVICE_COUNT] 启动 adapter :$PORT"

  LOG="/mnt/share/duanchengzhen/logs/${HOST_IP}/mobile_gym_adapter_${PORT}.log"
  MOBILEGYM_ENV_URL="$MOBILEGYM_ENV_URL" \
  MOBILEGYM_HEADLESS="${MOBILEGYM_HEADLESS:-1}" \
    nohup "$PYTHON_BIN" -m bench_env.server.env_server \
      --host 0.0.0.0 --port "$PORT" > "$LOG" 2>&1 &
  PID=$!
  ADAPTER_PIDS+=("$PID")
  DECLARED_PORTS+=("$PORT")
  echo "    PID=$PID  日志=$LOG  url=http://${HOST_IP}:${PORT}"
  sleep 1
done

echo "--------------------------------------------------"
echo "✅ adapter 启动完成，共 ${#DECLARED_PORTS[@]} 个"

if [ "${#DECLARED_PORTS[@]}" -eq 0 ]; then
  echo "ERROR: 没有成功启动任何 adapter" >&2
  bash scripts/server/start_nginx_gateway.sh stop >/dev/null 2>&1 || true
  exit 1
fi

# --- 3. 心跳上报守护进程（对齐 mobile_world：心跳由宿主机脚本统一发）---
PORTS_STR="${DECLARED_PORTS[*]}"
nohup bash -c "
# MOBILEGYM_HEARTBEAT  <- 进程标记，供 cleanup_stale 的 pkill -f 精确匹配，勿删
while true; do
  for PORT in $PORTS_STR; do
    curl -sS -m 5 -X POST '${GATEWAY_URL}' \
      -H 'Content-Type: application/json' \
      -d '{\"environment\":\"mobile_gym\",\"url\":\"http://${HOST_IP}:'\$PORT'\"}' > /dev/null 2>&1
  done
  sleep 30
done
" > /mnt/share/duanchengzhen/logs/${HOST_IP}/mobile_gym_heartbeat.log 2>&1 &
HEARTBEAT_PID=$!

echo "Heartbeat PID: $HEARTBEAT_PID  (每 30s 上报 ${#DECLARED_PORTS[@]} 个 device)"
echo "✅ 全部服务已注册到网关: $GATEWAY_URL"
echo ""
echo "停止方式："
echo "  kill $HEARTBEAT_PID ${ADAPTER_PIDS[*]}"
echo "  bash scripts/server/start_nginx_gateway.sh stop"
