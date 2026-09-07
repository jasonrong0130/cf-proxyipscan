# CF优选IP筛选器

一个轻量的 **本地 ProxyIP / Cloudflare 候选 IP 测试与筛选工具**。核心使用 Go，本地 Web UI 使用原生 HTML / CSS / JavaScript，不依赖 Electron。

## 当前定位

VPS 端可以负责大规模海选；本工具负责在 Windows / macOS / Linux **当前真实网络**下进行本地测试、筛选、排序、测速和导出。

本项目不再替用户把不同地区节点简单划分为“优质 / 可用 / 边缘”。香港、美国、日本等节点的物理距离不同，延迟数值本身只作为事实数据展示，是否适合使用由用户结合地区、线路、ASN、速度等自行判断。

当前 ProxyIP 本地测试遵循：

- 默认每个 IP 测试 1 次；高级设置可手动改为 1–5 次。
- SNI 默认留空；建议填入实际使用的 SNI。
- Host 默认跟随 SNI，仅在高级设置中允许单独覆盖。
- SNI 留空时只做 TCP 本地测试，不使用固定公共域名代替。
- 填写 SNI 后记录 TCP、TLS、TTFB、HTTP 状态、Cloudflare 证据、机房和出口 IP。
- HTTP 4xx / 5xx 只记录真实响应，不因为状态码直接把候选删除。
- `/cdn-cgi/trace` 没有 `colo` 只显示未知，不作为一票淘汰条件。
- 入口 / 出口 ASN 与组织信息使用本地 GeoLite2 ASN 数据库查询。
- 结果页支持分页、搜索、状态 / 端口 / 机房 / ASN / 延迟 / 速度筛选和表头排序。
- 支持当前筛选、当前页、已勾选、全部结果四种操作范围。
- 支持一键测速、继续测速、一键复制、TXT / CSV 导出。
- 测速只写入速度结果，不改变节点测试状态。

## 使用流程

1. 导入候选 `IP:端口` 的 TXT / CSV。
2. 需要真实 TLS / HTTP 链路验证时填写实际 SNI；只想看 TCP 时可留空。
3. 点击“开始测试”。
4. 在结果表中按机房、ASN、TCP、TTFB、速度等自行筛选与排序。
5. 对当前筛选 / 当前页 / 已勾选结果执行一键测速、复制或导出。

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
