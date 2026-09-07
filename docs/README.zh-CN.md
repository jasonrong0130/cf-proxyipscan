# ProxyIP Optimizer 使用说明

ProxyIP Optimizer 用于在当前电脑的真实本地网络环境中，对已经筛出的 ProxyIP 候选做最终优选。

## 推荐流程

1. 从 VPS 端 ProxyIP Scanner 导出可进入 EDT 的 `IP:端口` 候选。
2. 在本机运行 ProxyIP Optimizer。
3. 导入 TXT / CSV，或直接粘贴候选。
4. 填写实际使用的 SNI。Host 默认自动跟随 SNI；只有特殊配置才需要在高级设置中覆盖。
5. 默认使用“标准”模式；需要快速初筛可用“极速”，最终 Top 节点复核可用“精准”。
6. 优先看“优质 / 可用”，同时保留“边缘”结果用于人工复核，避免单次探测把实际可用节点误杀。

## 判定原则

- 不以固定公共域名作为 ProxyIP 是否可用的唯一依据。
- TCP、TLS、HTTP 分阶段记录，多次复检。
- 有效 HTTP 4xx/5xx 响应也能证明实际 HTTP 链路已经建立，不直接判死。
- Cloudflare Header / CF-Ray / trace 信息用于增强确认，而不是缺一项就淘汰。
- trace 缺少 `colo` 只表示机房信息未知。
- 精准模式参考测速只用于排名，不反向否定已经验证通过的真实链路。

## 本地安全

默认只监听 `127.0.0.1:13335`。SNI / Host 等用户输入只保存在当前浏览器 localStorage 中，源码不包含个人域名默认值。
