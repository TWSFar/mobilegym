# MobileGym 项目导览

## 1. 项目定位

MobileGym 是一个运行在浏览器中的 Android 风格移动环境，主要用于移动 GUI Agent 的训练、评测和轨迹数据生成。

它并不启动真正的 Android 模拟器，而是使用 React 实现手机桌面、系统 UI、系统服务和各种 App，再由 Python Benchmark 环境通过 Playwright 控制页面。Agent 只能看到截图，并通过点击、输入、滑动、返回等操作完成任务。

项目的核心能力包括：

- 可编程、可重置、可快照的完整环境状态
- Android 风格的 Task、Activity、Intent 和返回栈
- 微信、支付宝、地图、设置等模拟应用
- 基于结构化状态的确定性任务判定
- 多浏览器实例并行评测
- 自动生成导航图、动作任务和轨迹数据

主要技术栈：

- React 19、TypeScript、React Router
- Vite 6、Tailwind CSS 4
- Zustand 状态管理
- Python、Playwright
- Vitest、ESLint

## 2. 整体架构

```text
GUI Agent
   │  截图、点击、输入、滑动
   ▼
Python Benchmark（bench_env）
   │  Playwright / 真机控制
   ▼
浏览器中的模拟手机
   ├── OS 层：桌面、任务栈、通知、权限、键盘
   ├── App 层：微信、支付宝、地图等
   └── 状态层：Zustand、localStorage、Provider
   │
   ▼
结构化状态 Judge
   └── 成功率、任务进度、意外副作用等指标
```

代码主要分成四部分：

1. `os/`：模拟 Android 系统。
2. `apps/` 和 `system/`：第三方应用与系统应用。
3. `bench_env/`：Agent 执行、任务管理和结果判定。
4. `scripts/`：导航分析、任务生成和开发工具。

## 3. 根目录重要文件

### `index.tsx`

前端启动入口，负责：

- 初始化存储隔离和系统 Provider
- 初始化模拟时间、定位和皮肤
- 设置手机画布缩放比例
- 挂载 `OSProvider`、`ThemeProvider`、`BootGate` 和 `SystemShell`
- 暴露页面布局调试接口

大致启动流程：

```text
index.html
  → index.tsx
  → OSProvider
  → ThemeProvider
  → BootGate
  → SystemShell
  → Launcher 或具体 App
```

### `index.html`

Vite 使用的 HTML 模板，包含 React 根节点。

### `app.css`

项目全局样式，包括模拟手机的基础布局、系统级样式和 Tailwind 相关内容。

### `package.json`

定义前端依赖和常用命令：

```bash
npm run dev       # 启动开发服务器
npm run build     # 构建生产版本
npm run preview   # 预览构建结果
npm run test      # 运行 Vitest
npm run lint      # 检查 os/、apps/ 和 Store Getter
```

### `vite.config.ts`

除了普通 Vite 配置，还实现了一些开发服务器插件，例如：

- HTTP 请求日志
- `public/` 文件发现接口
- 模拟 SD 卡文件扫描
- 运行记录和静态资源辅助接口
- 构建时生成文件系统清单

### `AGENTS.md`

仓库开发规范，包含导航、状态、国际化、图标、文件边界和验证命令等规则。修改代码前应先检查这里的要求。

## 4. `os/`：模拟 Android 系统

`os/` 是整个项目的系统层，负责模拟 Android 的应用生命周期、任务栈、系统服务和系统界面。

### 核心协调文件

#### `os/OSContext.tsx`

系统总协调器，组合 TaskManager、IntentResolver、BackDispatcher 和各类服务。

它还会向浏览器暴露主要运行时 API：

- `window.__OS__`：启动应用、发送 Intent、读取系统服务等
- `window.__SIM__`：重置、注入和读取模拟器状态
- `window.__SIM_TIME__`：控制模拟时间
- `window.__SIM_LOCATION__`：控制模拟位置
- `window.__SIM_FS__`：访问模拟文件系统

#### `os/SystemShell.tsx`

模拟手机的可视化外壳，负责：

- 桌面和应用显示区域
- 状态栏和底部手势条
- 最近任务页面
- 边缘返回、Home 和多任务手势
- 通知栏、权限弹窗、系统键盘
- App 前后台显示与 `adjustResize`

#### `os/TaskManager.ts`

管理 Android 风格的 Task 和 Activity 栈，包括：

- 创建和激活任务
- Activity 入栈、出栈
- Home 和最近任务
- 关闭 Task 或 App
- 跨 App 启动后的返回关系

#### `os/IntentResolver.ts`

处理应用间 Intent：

- 按 Manifest 查找匹配的 App
- 显示 Intent 应用选择器
- 启动目标 Activity
- 支持 `startActivityForResult`

#### `os/BackDispatcher.ts`

统一分发系统返回操作。键盘、权限弹窗、通知栏和 App 页面可以按照优先级注册返回处理器。

#### `os/AppNavigatorRegistry.ts`

连接 OS Task/Activity 与 App 内部 React Router，使 OS 可以让指定 App 跳转到某个路径。

### App 自动发现

#### `os/data/appRegistry.tsx`

通过 `import.meta.glob` 自动发现：

- `apps/*/*App.tsx`
- `system/*/*App.tsx`
- 可选的 `data/loader.ts`

App 会按需加载，并由 React `Suspense` 和错误边界处理加载状态。因此新增 App 通常不需要修改 OS 注册表。

### 状态与数据

#### `os/OsStateStore.ts`

保存 Android 数据模型中的系统状态，例如：

- 系统、全局和安全设置
- 电池、Wi-Fi、蓝牙、蜂窝网络
- 权限和用户偏好

#### `os/createOsStore.ts`

创建系统层 Zustand Store，并将 Store 注册到统一状态快照系统。

#### `os/createAppStore.ts`

创建 App Store，处理 App 状态注册、持久化、读取和重置。

#### `os/providers/`

实现跨 App 共享数据源：

- `ContactsProvider.ts`：联系人
- `SmsProvider.ts`：短信
- `MediaProvider.ts`：图片、视频等媒体
- `SystemWidgetProvider.ts`：系统小组件数据

App 通过 `ContentResolver` 查询和修改这些数据。

### 系统服务

常用系统服务包括：

| 文件 | 功能 |
| --- | --- |
| `TimeService.ts` | 真实时间、模拟时间、时间加速 |
| `LocationService.ts` | 模拟定位和定位错误 |
| `NetworkService.ts` | 统一网络请求和代理 |
| `FileSystemService.ts` | 模拟文件系统 |
| `NotificationService.ts` | 系统通知 |
| `PermissionService.ts` | 权限请求与授权 |
| `ClipboardService.ts` | 剪贴板和历史记录 |
| `MediaService.ts` | 媒体选择和媒体操作 |
| `StatusBarService.ts` | 状态栏外观和动态状态 |
| `QuickSettingsService.ts` | 快捷设置 |
| `SystemShadeService.ts` | 通知栏和控制中心 |
| `SmsGateway.ts` | 短信发送与接收接口 |

### Agent 输入接口

#### `os/simInput.ts`

实现 Agent 使用的原子操作：

- `tap`
- `doubleTap`
- `longPress`
- `type`
- `swipe`
- `drag`
- `back`
- `home`
- `recent`
- `enter`

这些操作以坐标和 PointerEvent 为基础，使不同 Agent 使用相同的输入语义。

#### `os/hooks/useTriggerGestures.ts`

为 App 控件添加标准化的：

- `data-trigger`
- `data-trigger-type`
- `data-action`
- `data-action-type`

这些属性供导航检查、任务生成和轨迹分析使用。Agent 本身仍然只观察截图。

### 其他子目录

- `os/components/`：状态栏、通知、键盘、权限弹窗等系统组件。
- `os/keyboard/`：拼音输入法和键盘服务。
- `os/launcher/`：桌面布局、文件夹、图标拖动和小组件。
- `os/managers/`：网络、电池、音频、亮度等硬件管理器。
- `os/hooks/`：导航、主题、剪贴板、虚拟列表等公共 Hook。
- `os/types/`：Manifest、Intent、Provider 和全局 API 类型。

## 5. `apps/` 与 `system/`：应用层

### 第三方应用 `apps/`

当前代码目录包括：

- Alipay
- Bilibili
- Ebay
- Map
- Railway12306
- RedBook
- Reddit
- Spotify
- TencentMeeting
- Weather
- Wechat
- WechatReading
- X

### 系统应用 `system/`

当前代码目录包括：

- AnswerSheet
- Browser
- Calculator
- Calculator2
- Calendar
- Clock
- Compass
- Contacts
- FileManager
- Gallery
- Notes
- Settings
- Sms
- ThemeStore

从目录看共有 13 个第三方 App 和 14 个系统 App。README 中使用了“28 个模拟 App”的口径，可能将 Launcher 或其他系统入口也计算在内。

### 一个 App 的标准结构

以 `apps/Wechat/` 为例：

```text
Wechat/
├── manifest.ts
├── WechatApp.tsx
├── navigation.declaration.ts
├── navigation.ts
├── navigation.types.ts
├── state.ts
├── constants.ts
├── types.ts
├── data/
│   ├── defaults.json
│   └── index.ts
├── res/
│   ├── strings.ts
│   ├── strings.en.ts
│   ├── colors.ts
│   ├── icons.tsx
│   └── dimens.ts
├── hooks/
├── components/
└── pages/
```

各文件的职责如下。

#### `manifest.ts`

类似 AndroidManifest，声明：

- App ID 和包名
- 中英文名称
- 图标和主题
- 启动模式
- 权限
- Intent Filter 和 Deep Link

#### `*App.tsx`

App 的 React 入口，一般包含：

- `MemoryRouter`
- `<Routes>` 和页面组件注册
- App 导航处理器
- 主 Tab 布局
- 主题资源和 CSS 变量

该文件必须默认导出组件，OS 才能自动发现。

#### `navigation.declaration.ts`

声明 App 的完整导航状态机，包括：

- 页面 Route
- 页面内 UI State
- Transition
- Action
- 查询参数
- 滚动容器

它既是导航文档，也是导航图和动作任务的生成源。

#### `navigation.ts`

向业务页面提供 `go()` 和 `back()`。业务页面不应直接调用 React Router 的 `useNavigate()`。

#### `hooks/use<AppName>Gestures.ts`

封装该 App 的点击、返回和动作标记，确保 DOM 属性与导航声明一致。

#### `state.ts`

App 的 Zustand Store，保存用户数据、业务数据和设置，并接入模拟器状态快照。

#### `data/defaults.json`

保存可替换的初始数据，例如：

- 用户信息
- 消息和订单
- 浏览历史
- 用户设置
- 用户配置的首页布局

#### `constants.ts`

保存固定的产品结构，例如 Tab、服务目录、布局参数和功能开关。

#### `res/`

App 资源目录：

- `strings.ts`：默认文案
- `strings.en.ts`：英文覆盖
- `colors.ts`：品牌色和特殊颜色
- `icons.tsx`：App 图标别名
- `dimens.ts`：复用尺寸

#### `pages/` 与 `components/`

- `pages/`：完整业务页面。
- `components/`：多个页面共享的列表项、顶部栏、TabBar 等组件。

## 6. `bench_env/`：Agent Benchmark

`bench_env/` 是 Python 评测框架，负责启动环境、执行任务、调用 Agent、记录轨迹和判断结果。

### `bench_env/run.py`

命令行入口，可以：

- 列出任务
- 运行单个任务或 Suite
- 运行 train/test split
- 选择 Agent
- 设置并发量
- 连接模拟器或真实设备
- 生成运行日志和统计结果

### `bench_env/env/`

- `mobile_gym.py`：Playwright 模拟器环境。
- `real_device.py`：真实 Android 设备环境。
- `pool.py`：并行浏览器和页面池。
- `recorder.py`：截图、动作和轨迹记录。
- `base.py`：环境公共接口。

### `bench_env/agent/`

不同 Agent 的适配器，包括：

- AutoGLM
- GUI-Owl
- UI-TARS
- UI-Venus
- MAI-UI
- Generic OpenAI 格式 Agent
- Human 手动模式

### `bench_env/runner/`

任务调度方式：

- `serial.py`：串行执行
- `parallel.py`：并行执行
- `multiprocess.py`：多进程执行
- `exec.py`：自由指令执行

### `bench_env/task/`

任务系统的核心：

- `base.py`：任务、参数和 Judge 基础类型。
- `judge.py`：结构化状态判定。
- `vlm_judge.py`：真实设备或指定场景下的 VLM 判定。
- `registry.py`：任务注册与发现。
- `sampler.py`：参数化任务采样。
- `<suite>/tasks.py`：具体 App 或跨 App 任务。

Judge 可以直接检查任务后的 JSON 状态，例如：

- 指定消息是否发送
- 某项设置是否改变
- 联系人是否新增
- 余额或订单状态是否正确
- 是否产生未授权的额外修改

### `bench_env/splits/`

保存任务划分：

- `train.txt`
- `test.txt`
- `payment.txt`
- `high_risk.txt`
- Sim-to-Real 指令集合

## 7. `scripts/`：开发工具

### 导航与任务生成

- `build_nav_artifacts.mjs`：一次性执行导航检查、图生成和动作任务生成。
- `check_navigation_declaration_consistency.mjs`：检查声明和代码绑定是否一致。
- `navigation_declaration_analyzer.mjs`：生成导航图或数据图。
- `generate_action_tasks_from_nav_graph.mjs`：从导航图生成动作任务。
- `nav_path_finder.py`：查找页面间最短路径。

修改 App 导航声明或新增页面后，应执行：

```bash
node scripts/build_nav_artifacts.mjs <AppName>
```

### 其他工具

- `lint_store_getters.mjs`：检查 Zustand Getter 反模式。
- `dev/dump_app_state_schema.py`：导出 App 状态结构。
- `dev/prepare-themes.py`：处理主题数据。
- `ime/build_pinyin_dict.mjs`：生成拼音输入法词典。
- `server/start_nginx_gateway.sh`：启动适合高并发 Benchmark 的 Nginx Gateway。
- `server/api_gateway.py`：开发和 Benchmark 使用的后端网关。

## 8. `docs/`：项目文档

### `docs/platform/`

平台实现规范，是开发时最重要的参考：

- `architecture.md`：整体架构
- `app/module-contract.md`：App 文件和资源契约
- `navigation/declaration.md`：导航声明规范
- `navigation/actions.md`：Action 规范
- `state/model.md`：状态和数据模型
- `os/overview.md`：OS 层概览
- `os/task-lifecycle.md`：Task/Activity 生命周期
- `os/intent-system.md`：Intent 系统
- `tooling/i18n.md`：国际化规范

### `docs/guides/`

面向具体任务的操作指南：

- 添加 App
- 添加 Agent
- 添加 Benchmark 任务
- 运行 Agent Benchmark

### `docs/api/`

说明运行时 API 和完整状态快照结构。

### `bench_env/docs/`

说明 Benchmark 架构、CLI 参数、任务编写和离线测试规则。

## 9. `public/` 与静态资源

`public/` 保存无需经过 TypeScript 打包的资源，包括：

- 系统 SVG 图标
- Tailwind 构建样式
- 运行轨迹查看页面 `run_explorer.html`
- 导航图和任务生成产物
- 模拟 SD 卡静态文件

App 自己使用的图片、字体和其他二进制资源通常应放在对应 App 的 `assets/` 中，并通过 Vite `import` 加载。

## 10. 一次任务的典型执行过程

```text
1. bench_env 加载任务模板和参数
2. 通过 __SIM__.reset() 重置模拟器
3. 通过 __SIM__.setState() 注入任务初始状态
4. Agent 获取当前手机截图
5. Agent 输出点击、输入、滑动等操作
6. bench_env 通过 __SIM_INPUT__ 或 Playwright 执行操作
7. 重复截图和操作，直到 Agent 完成或超时
8. Judge 读取 __SIM__.getState()
9. 对比目标状态和意外副作用
10. 输出成功率、进度和运行轨迹
```

## 11. 推荐阅读顺序

第一次了解项目时，可以按照下面的顺序阅读：

1. `README.md`
2. `index.tsx`
3. `os/SystemShell.tsx`
4. `os/OSContext.tsx`
5. `os/TaskManager.ts`
6. `os/data/appRegistry.tsx`
7. 一个简单系统 App 的 `manifest.ts` 和 `*App.tsx`
8. `apps/Wechat/navigation.declaration.ts`
9. `bench_env/run.py`
10. `bench_env/env/mobile_gym.py`
11. `bench_env/task/base.py` 和 `judge.py`

如果准备开发新功能，则优先阅读对应的 `docs/platform/` 规范，代码与描述性文档不一致时以实际代码为准；与强制性规范不一致时，应先确认是代码缺陷还是规范需要更新。

## 12. 作为 Mobile World 风格的 HTTP 环境服务

### 12.1 结论

MobileGym 可以实现 Mobile World 那种“启动许多独立环境，每个环境通过 HTTP 提供截图、任务和动作接口”的部署方式，而且当前仓库已经有一个单实例 HTTP 适配器：

```text
bench_env/server/env_server.py
```

它已经提供了任务列表、任务难度、任务初始化、截图、动作执行、任务判定和健康检查等接口。

两者的底层实例不同：

| 对比项 | Mobile World | MobileGym |
| --- | --- | --- |
| 移动环境 | Android Emulator | Chromium 中的 React 模拟手机 |
| 一个实例 | 一个 Emulator | 一个 `MobileGymEnv` / Playwright Page |
| 动作执行 | ADB 或设备控制服务 | Playwright + `__SIM_INPUT__` |
| 截图 | Emulator 截屏 | Playwright Page 截图 |
| 初始化 | 修改设备或 App 数据 | `task.setup()` + `__SIM__.setState()` |
| 判定 | 设备状态或视觉 Judge | 结构化 JSON 状态 Judge |
| 扩容成本 | 相对较高 | Page、Context 或 Browser 级轻量扩容 |

因此 MobileGym 不需要为每个实例启动 Android Emulator。要复刻相同的外部协议，只需要为每个 `MobileGymEnv` 增加一层 HTTP Adapter。

### 12.2 当前已有的 HTTP 服务

`bench_env/server/env_server.py` 使用 FastAPI 包装一个 `MobileGymEnv`。它的基本模型是：

```text
一个 env_server 进程
    ├── 一个 FastAPI HTTP 端口
    ├── 一个 MobileGymEnv
    ├── 一个 Chromium Browser/Context/Page
    ├── 一个当前 Task
    ├── 一份初始 Observation
    └── 一把 asyncio.Lock
```

当前端点：

| 方法 | 路径 | 功能 |
| --- | --- | --- |
| `GET` | `/health` | 服务健康检查 |
| `POST` | `/init` | 延迟创建浏览器环境 |
| `GET` | `/screenshot` | 获取 Base64 截图和当前 App |
| `POST` | `/step` | 执行点击、输入、滑动等动作 |
| `POST` | `/task/init` | 创建并初始化一个任务 |
| `POST` | `/task/tear_down` | 清理当前任务上下文 |
| `GET` | `/task/eval` | 对当前任务进行结构化判定 |
| `GET` | `/task/goal` | 获取任务指令 |
| `GET` | `/task/complexity` | 将 L1～L4 映射成 1.0～4.0 |
| `GET` | `/task/list` | 获取所有任务 ID |

HTTP 服务内部直接复用了现有能力：

| HTTP 能力 | 复用的 MobileGym 代码 |
| --- | --- |
| 任务发现 | `TaskRegistry.list_suites()`、`list_tasks()` |
| 任务难度 | Task Class 的 `difficulty` |
| 任务初始化 | `task.setup(env)` |
| 截图 | `env.get_observation()` |
| 动作 | `env.step(Action(...))` |
| 当前状态 | `env.get_state()` |
| 任务判定 | `task.evaluate(JudgeInput(...))` |
| 环境清理 | `env.close()` |

这意味着任务逻辑、参数采样和 Judge 不需要重写。

### 12.3 启动一个服务

先启动 MobileGym 静态前端：

```bash
npm run build
npm run preview -- --port 4173
```

再启动一个环境服务：

```bash
MOBILEGYM_ENV_URL=http://127.0.0.1:4173 \
python -m bench_env.server.env_server --port 8100
```

也可以直接使用 Uvicorn：

```bash
MOBILEGYM_ENV_URL=http://127.0.0.1:4173 \
uvicorn bench_env.server.env_server:app \
  --host 0.0.0.0 \
  --port 8100 \
  --workers 1
```

注意：`bench_env/requirements.txt` 当前没有显式声明 `fastapi`、`uvicorn` 和 `httpx`。正式使用这一服务前，应将它们加入依赖文件并固定兼容的版本。

这里必须保持 `--workers 1`。当前服务使用进程内全局 `STATE` 保存浏览器和任务；如果同一端口启动多个 Uvicorn Worker，请求可能被不同进程处理，导致 `/task/init`、`/step` 和 `/task/eval` 操作到不同实例。

### 12.4 调用示例

初始化环境：

```bash
curl -X POST http://127.0.0.1:8100/init \
  -H 'Content-Type: application/json' \
  -d '{"device":"mobile_gym"}'
```

获取任务列表：

```bash
curl http://127.0.0.1:8100/task/list
```

获取任务难度：

```bash
curl 'http://127.0.0.1:8100/task/complexity?task_name=wechat.ReadMyWxid'
```

初始化任务：

```bash
curl -X POST http://127.0.0.1:8100/task/init \
  -H 'Content-Type: application/json' \
  -d '{"task_name":"wechat.ReadMyWxid","req_device":"mobile_gym"}'
```

获取截图：

```bash
curl http://127.0.0.1:8100/screenshot
```

执行归一化坐标点击。当前服务使用 0～1000 坐标系，与设备实际分辨率无关：

```bash
curl -X POST http://127.0.0.1:8100/step \
  -H 'Content-Type: application/json' \
  -d '{
    "device":"mobile_gym",
    "action":{"action_type":"click","x":500,"y":700}
  }'
```

输入文本：

```bash
curl -X POST http://127.0.0.1:8100/step \
  -H 'Content-Type: application/json' \
  -d '{
    "device":"mobile_gym",
    "action":{"action_type":"input_text","text":"Hello"}
  }'
```

滑动：

```bash
curl -X POST http://127.0.0.1:8100/step \
  -H 'Content-Type: application/json' \
  -d '{
    "device":"mobile_gym",
    "action":{"action_type":"swipe","x":500,"y":750,"x2":500,"y2":250}
  }'
```

判定任务：

```bash
curl 'http://127.0.0.1:8100/task/eval?task_name=wechat.ReadMyWxid&req_device=mobile_gym'
```

### 12.5 当前支持的动作

HTTP Adapter 会把外部 JSON Action 转换成 `bench_env.env.base.Action`：

- `click` / `tap`
- `double_tap`
- `long_press`
- `input_text` / `type`
- `keyboard_enter`
- `navigate_back` / `back`
- `navigate_home` / `home`
- `open_app`
- `scroll`
- `swipe`
- `drag`
- `wait`
- `answer`
- `complete` / `abort`

`MobileGymEnv.step()` 执行动作后会等待短暂的 UI 稳定时间。HTTP Adapter 随后重新获取包含完整状态的 Observation，供 `/task/eval` 使用。

### 12.6 多实例、多端口部署

如果希望完全复刻 Mobile World 的“一台设备对应一个端口”，可以启动多个 `env_server` 进程：

```text
共享静态前端 :4173
    ├── env_server :8100 → Chromium A → MobileGymEnv A
    ├── env_server :8101 → Chromium B → MobileGymEnv B
    ├── env_server :8102 → Chromium C → MobileGymEnv C
    └── env_server :8103 → Chromium D → MobileGymEnv D
```

每个进程都设置相同的 `MOBILEGYM_ENV_URL`，但绑定不同的 HTTP 端口。每个进程拥有独立的浏览器 Context 和任务状态，因此客户端可以把每个 URL 当成一台独立设备。

生产环境不建议手工维护大量端口，应增加一个进程管理器，例如：

```text
Env Service Manager
    ├── 分配空闲端口
    ├── 启动 env_server 子进程
    ├── 等待 /health Ready
    ├── 返回 instance_id、URL 和租约
    ├── 心跳与超时回收
    └── 进程退出后清理端口和 Chromium
```

建议管理接口：

| 方法 | 路径 | 功能 |
| --- | --- | --- |
| `POST` | `/instances` | 创建一个环境，返回实例 ID 和服务 URL |
| `GET` | `/instances` | 查询全部实例与状态 |
| `GET` | `/instances/{id}` | 查询某个实例 |
| `DELETE` | `/instances/{id}` | 关闭服务并回收端口 |
| `POST` | `/instances/{id}/renew` | 续租，避免空闲回收 |

创建响应可以使用：

```json
{
  "instance_id": "mg-01JABC...",
  "url": "http://host:8107",
  "status": "ready",
  "expires_at": 1787300000
}
```

### 12.7 更推荐的大规模方案：单端口、多实例

端口与环境一一对应便于兼容 Mobile World，但在数百实例规模下，端口管理、进程数量和健康检查都会变复杂。

MobileGym 已有 `EnvPool`，可以在一个或多个 Browser 中创建多个环境：

- `pages`：一个 Context 中多个 Page，最轻量。
- `contexts`：一个 Browser 中多个 Context，存储隔离更强。
- `browsers`：每个实例一个 Browser，隔离最强、资源最多。

因此新系统更适合使用一个统一端口加 `instance_id`：

```text
Client
   │ HTTP :8100
   ▼
Environment Service
   ├── /instances/a/... → MobileGymEnv A
   ├── /instances/b/... → MobileGymEnv B
   ├── /instances/c/... → MobileGymEnv C
   └── /instances/d/... → MobileGymEnv D
```

建议端点：

```text
POST   /v1/instances
DELETE /v1/instances/{instance_id}
POST   /v1/instances/{instance_id}/reset
GET    /v1/instances/{instance_id}/screenshot
GET    /v1/instances/{instance_id}/observation
GET    /v1/instances/{instance_id}/state
POST   /v1/instances/{instance_id}/actions
POST   /v1/instances/{instance_id}/tasks/{task_id}/init
GET    /v1/instances/{instance_id}/tasks/current
POST   /v1/instances/{instance_id}/tasks/current/evaluate
GET    /v1/tasks
GET    /v1/tasks/{task_id}
```

这种模式可以复用 `EnvPool`，减少 Chromium 进程数量，并通过 Nginx 或 Gateway 对外只暴露一个端口。如果已有客户端强制要求“一设备一 URL”，Gateway 仍然可以给每个实例分配虚拟 URL，再转发到统一服务。

### 12.8 Docker 部署方式

可以制作一个包含以下内容的镜像：

- MobileGym 前端构建产物 `dist/`
- Chromium 和 Playwright 运行依赖
- Python `bench_env`
- FastAPI/Uvicorn 环境服务
- Nginx 静态资源服务

有三种部署拓扑。

#### 方案 A：一个容器一个实例

```text
container-1 :8100 → env_server → Chromium
container-2 :8101 → env_server → Chromium
container-3 :8102 → env_server → Chromium
```

优点是隔离和 Mobile World 最接近；缺点是重复启动 Chromium 和静态服务，资源开销较大。

更合理的变体是让所有容器访问同一个外部 MobileGym 静态前端，每个实例容器只运行 `env_server + Chromium`。

#### 方案 B：一个容器多个端口

```text
container
├── Nginx :4173
├── env_server :8100
├── env_server :8101
├── env_server :8102
└── env_server :8103
```

需要 Supervisor、s6、systemd 或自定义 Python Manager 管理子进程。适合必须保持一实例一端口协议的情况。

#### 方案 C：一个容器一个多实例 API

```text
container
├── Nginx :4173
└── Environment Service :8100
      └── EnvPool → N 个 Page/Context/Browser
```

这是最符合 MobileGym 架构的方式，部署简单，也更容易实现动态扩缩容。

### 12.9 实现时必须处理的问题

#### 1. 请求串行化

同一个实例的 `task/init`、`step`、`screenshot` 和 `eval` 不能并发修改页面。当前单实例服务使用 `asyncio.Lock` 串行化操作。多实例服务应该为每个 `instance_id` 单独维护一把锁，而不是使用一把全局锁。

#### 2. Episode 身份

建议 `/task/init` 返回 `episode_id`，后续动作必须携带它。这样旧客户端的延迟请求不会误操作已经被重新初始化的任务。

```json
{
  "instance_id": "mg-001",
  "episode_id": "ep-001",
  "task_id": "wechat.ReadMyWxid"
}
```

#### 3. 动作顺序与幂等

为动作增加递增的 `action_id` 或 `sequence`。服务端拒绝重复或乱序动作，避免网络重试导致一次点击执行两遍。

#### 4. 截图协议

当前 `/screenshot` 返回字段名 `b64_png`，但底层 `MobileGymEnv` 实际生成的是 JPEG。兼容既有 Gateway 时可以保留字段名；新 API 应明确返回：

```json
{
  "mime_type": "image/jpeg",
  "data_base64": "...",
  "width": 1080,
  "height": 2400,
  "step": 3
}
```

也可以直接返回 `image/jpeg` 二进制响应，减少 JSON 和 Base64 的额外开销。

#### 5. 任务参数

当前 `/task/init` 只接收 `task_name`，任务参数使用默认值或 Task 自身的采样器生成。如果调用方需要指定参数，应扩展请求：

```json
{
  "task_name": "wechat.SomeTask",
  "params": {
    "contact": "张三",
    "message": "你好"
  },
  "seed": 42
}
```

服务端可以调用 `TaskRegistry.create_task(task_name, **params)`，并确保 seed 被记录到 Episode 元数据中。

#### 6. 实例隔离

- 调试或低风险场景可以使用 `pages`。
- 长时间运行的共享服务建议至少使用 `contexts`。
- 不可信租户、故障隔离或严格 Benchmark 可以使用 `browsers` 或独立容器。

#### 7. 超时和资源回收

每个实例应记录：

- 创建时间
- 最后访问时间
- 当前任务和步骤数
- 浏览器 PID
- 健康状态
- 租约到期时间

超过 TTL 后调用 `env.close()`，确保 Page、Context、Browser 和 Playwright 都被释放。

#### 8. 服务健康检查

`/health` 只能说明 HTTP 进程存活。生产环境还需要 `/ready`，实际检查：

- Chromium 是否存活
- Page 是否可执行 JavaScript
- `window.__SIM__` 是否存在
- 前端静态资源是否加载完成

#### 9. 安全边界

不要直接把状态注入、文件系统和任意 URL 代理接口暴露到公网。至少需要：

- API Token 或 mTLS
- 请求体大小限制
- 动作速率限制
- 允许的任务和 App 白名单
- 外部网络访问策略
- 每租户的实例配额

#### 10. 可观测性

建议暴露 Prometheus 指标：

- 活跃/空闲/故障实例数
- 初始化耗时
- 截图耗时
- 动作执行耗时
- Task Setup 和 Judge 耗时
- Chromium 重启次数
- 每个实例的内存占用

### 12.10 推荐落地顺序

#### 第一阶段：验证已有单实例服务

1. 将 FastAPI、Uvicorn、HTTPX 加入依赖。
2. 启动前端 `:4173` 和一个 `env_server :8100`。
3. 验证 `/task/list`、`/task/init`、`/screenshot`、`/step`、`/task/eval`。
4. 为端点增加自动化测试。

#### 第二阶段：完善单实例协议

1. 增加 `/ready`、`/state` 和二进制截图接口。
2. 为 Task Init 增加 `params` 和 `seed`。
3. 增加 `episode_id`、动作序列号和明确的错误码。
4. 修正截图 MIME 描述。
5. 增加认证、超时和指标。

#### 第三阶段：实现多端口管理器

1. 新建环境进程管理器。
2. 动态分配端口并启动 `env_server`。
3. 健康探测成功后注册到 Gateway。
4. 增加租约、心跳、崩溃重启和端口回收。
5. 提供 Docker Compose 或 Kubernetes 部署模板。

#### 第四阶段：实现原生多实例服务

1. 将 `env_server.py` 中的全局 `STATE` 改成 `instance_id → DeviceState` Registry。
2. 用 `EnvPool` 管理 Page/Context/Browser。
3. 所有实例级端点增加 `instance_id`。
4. 做负载测试后选择默认隔离级别和每个 Browser 的 Page 数量。

### 12.11 建议新增或修改的文件

如果正式实现这套服务，建议按职责拆分：

```text
bench_env/server/
├── env_server.py          # 保留兼容 Mobile World 的单实例协议
├── pool_server.py         # 单端口、多实例 API
├── instance_manager.py    # 生命周期、端口、租约、回收
├── models.py              # Pydantic 请求/响应模型
├── action_adapter.py      # JSON Action → MobileGym Action
├── metrics.py             # Prometheus 指标
└── tests/
    ├── test_env_server.py
    ├── test_pool_server.py
    └── test_action_adapter.py

deploy/
├── Dockerfile.env-server
├── docker-compose.env.yml
└── kubernetes/
```

如果目标是快速接入已有 Mobile World Gateway，优先直接使用并完善 `env_server.py`；如果目标是数十到数百实例的长期服务，优先实现基于 `EnvPool` 的单端口多实例 API。
