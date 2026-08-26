#!/usr/bin/env bash
# 抓取 env_server 当前模拟器画面，存成 png 并打印路径。
# 用法: bash bench_env/server/shot.sh [port] [out]
port="${1:-8100}"
out="${2:-/tmp/mg_shot.png}"
curl -s "http://127.0.0.1:${port}/screenshot" \
  | /home/mi/miniforge3/envs/mobile-gym/bin/python -c "
import sys, json, base64
d = json.load(sys.stdin)
img = base64.b64decode(d['b64_png'])
open('$out','wb').write(img)
print('app:', d.get('app_name'), '| bytes:', len(img), '->', '$out')
"
