# ProxyIP Optimizer

一个轻量的 **本地 ProxyIP 优选工具**，核心使用 Go，本地 Web UI 使用原生 HTML / CSS / JavaScript，不依赖 Electron。

## 当前目标

VPS 端负责大规模海选 ProxyIP；本工具负责在你的 Windows / macOS / Linux **当前真实网络**下进行最终优选。

与传统 CF 优选判定不同，本项目的 ProxyIP 模式遵循：

- 不使用固定 `speed.cloudflare.com` 作为“是否可用”的唯一标准。
- SNI 默认留空；建议填入你实际使用的 SNI。
- Host 默认跟随 SNI，仅在高级设置中允许单独覆盖。
- TCP / TLS / HTTP 多次复检，单次失败不会直接淘汰。
- HTTP 4xx / 5xx 只要真实 TLS + HTTP 链路建立成功，仍作为链路证据记录，不直接判死。
- `/cdn-cgi/trace` 没有 `colo` 不再一票否决。
- 失败节点分为“边缘”和“失败”，尽量减少实际可用节点被误杀。
- 精准模式的公共测速仅用于参考；测速失败不会改变真实可用判定。

## 使用流程

1. 从 VPS ProxyIP Scanner 导出候选 `IP:端口`。
2. 在本机运行 ProxyIP Optimizer。
3. 导入 TXT / CSV，填写实际 SNI。
4. 选择 极速 / 标准 / 精准。
5. 根据成功率、TCP、TLS、TTFB、CF 确认、参考速度和评分挑选 Top 节点。

SNI、Host 等个人配置只保存在浏览器 `localStorage`，源码默认值不包含任何个人域名。

## 构建

正式后端位于 `combined_refactor/`：

```bash
cd combined_refactor
go build -trimpath -ldflags "-s -w" -o proxyip-optimizer .
```

Windows：

```bash
cd combined_refactor
set GOOS=windows
set GOARCH=amd64
go build -trimpath -ldflags "-s -w" -o proxyip-optimizer.exe .
```

默认本地 Web 地址沿用后端监听端口 `13335`。

## License / Attribution

本项目基于 CFData-WEB 继续开发，并保留原项目 GPL-3.0-or-later 授权要求与版权信息。修改版继续采用 GNU General Public License v3.0 or later；详见 `LICENSE`。

在当前私有开发阶段仅用于内部测试。若未来公开或分发二进制版本，将按 GPL-3.0-or-later 要求同步提供对应源码与许可信息。
