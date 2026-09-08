# CF优选IP筛选器

一个轻量的 **本地 ProxyIP / Cloudflare 候选 IP 测试与筛选工具**。核心使用 Go，本地 Web UI 使用原生 HTML / CSS / JavaScript，不依赖 Electron。

## 当前定位

VPS 端可以负责大规模海选；本工具负责在 Windows / macOS / Linux **当前真实网络**下进行本地测试、筛选、排序、测速和导出。

本项目不再替用户把不同地区节点简单划分为“优质 / 可用 / 边缘”。香港、美国、日本等节点的物理距离不同，延迟数值本身只作为事实数据展示，是否适合使用由用户结合地区、线路、ASN、速度等自行判断。

当前 ProxyIP 本地测试遵循：

- 默认每个 IP 测试 1 次；高级设置可手动改为 1–5 次。
- SNI 必填；点击开始时未填写 SNI 会直接提示，不启动任务。
- Host 默认跟随 SNI，仅在高级设置中允许单独覆盖。
- “可优选”表示使用当前 SNI 完成 TCP → TLS → HTTP 并收到有效 HTTP 响应；其余归为失败。
- HTTP 4xx / 5xx 只要真实收到响应仍可作为链路可达证据，不因状态码直接淘汰。
- 记录 TCP、TLS、首包响应（TTFB）、Cloudflare 机房、出口 IP、ASN / 运营商和归属地。
- 归属地优先使用出口信息；出口位置拿不到时再回退查询入口 IP。
- 入口 / 出口 ASN 与组织信息使用本地 GeoLite2 ASN 数据库查询。
- 结果页只保留核心筛选：状态、测速结果和搜索，并支持 TCP / TLS / 首包响应 / 速度排序。
- 支持一键测速、继续测速、停止测速、一键复制。
- 导出支持：当前筛选结果、已勾选结果、全部可优选、全部结果。
- 测速只写入速度结果，不改变节点“可优选 / 失败”状态。
- 普通测试默认并发 8，可在高级设置提高，后端防呆上限 512；64 以上会明显增加连接与 CPU 占用。
- 测速默认并发 1，可手动提高到 16；测速属于持续下载任务，建议按机器性能逐步增加。
- 单节点测速采用轻量模式：最多约 5 秒 / 32MB，使用较大缓冲直接流式读取，避免高频小块 goroutine/channel 调度。

## 使用流程

1. 导入候选 `IP:端口` 的 TXT / CSV。
2. 填写实际使用的 SNI。
3. 点击“开始测试”。
4. 先筛选“可优选”，再按 TCP、TLS、首包响应等排序。
5. 需要时只对可优选节点执行批量测速。
6. 可继续筛选“测速成功”，再按速度排序。
7. 导出“当前筛选结果”或“已勾选结果”，也可以导出全部可优选 / 全部结果。

SNI、Host 等个人配置只保存在浏览器 `localStorage`，源码默认值不包含任何个人域名。

## 构建

正式后端位于 `combined_refactor/`：

```bash
cd combined_refactor
go build -trimpath -ldflags "-s -w" -o cf-ip-selector .
```

Windows：

```bash
cd combined_refactor
set GOOS=windows
set GOARCH=amd64
go build -trimpath -ldflags "-s -w" -o cf-ip-selector.exe .
```

默认本地 Web 地址为 `http://127.0.0.1:13335`，程序默认只监听本机回环地址，不会直接暴露到局域网或公网。

## License / Attribution

本项目基于 CFData-WEB 继续开发，并保留原项目 GPL-3.0-or-later 授权要求与版权信息。修改版继续采用 GNU General Public License v3.0 or later；详见 `LICENSE`。

在当前私有开发阶段仅用于内部测试。若未来公开或分发二进制版本，将按 GPL-3.0-or-later 要求同步提供对应源码与许可信息。
