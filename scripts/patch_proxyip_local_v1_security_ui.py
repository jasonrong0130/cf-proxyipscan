from pathlib import Path

root = Path('.')
go = root / 'combined_refactor'

main_path = go / 'main.go'
main = main_path.read_text(encoding='utf-8')
old = 'flag.StringVar(&listenHost, "host", "", "服务监听地址；留空监听全部地址，Android APK 建议使用 127.0.0.1")'
new = 'flag.StringVar(&listenHost, "host", "127.0.0.1", "服务监听地址；默认仅监听本机 127.0.0.1，需要局域网访问时再显式修改")'
if old not in main and new not in main:
    raise SystemExit('listenHost flag line not found')
main = main.replace(old, new, 1)
main_path.write_text(main, encoding='utf-8')

index_path = go / 'index.html'
html = index_path.read_text(encoding='utf-8')
html = html.replace("socket.onclose=()=>{if(running)toast('本地引擎连接已断开');setTimeout(connect,1800)}", "socket.onclose=()=>{if(running){toast('本地引擎连接已断开');finishRun()}setTimeout(connect,1800)}")
html = html.replace("function parseLocalCount(text){return text.split(/\\r?\\n/).map(x=>x.trim()).filter(x=>x&&!x.startsWith('#')).length}", "function parseLocalCount(text){return text.split(/\\r?\\n/).map(x=>x.trim()).filter(x=>x&&!x.startsWith('#')&&!(/^proxyip\\s*,\\s*port/i.test(x)||/^ip\\s*,\\s*port/i.test(x))).length}")
old_start = "running=true;$('startBtn').classList.add('hidden');$('stopBtn').classList.remove('hidden');$('progressTitle').textContent='准备开始';$('progressSub').textContent='本地链路验证';send('start_proxy_task',{fileName,fileContent:text,fallbackPort:Number($('fallbackPort').value||443),sni,host:$('host').value.trim(),path:$('path').value.trim()||'/cdn-cgi/trace',enableTLS:tls,mode,threads:Number($('threads').value||0),timeoutMs:Number($('timeoutMs').value||0),insecure,speedLimit:mode==='precise'?10:0})"
new_start = "running=true;$('startBtn').classList.add('hidden');$('stopBtn').classList.remove('hidden');$('progressTitle').textContent='准备开始';$('progressSub').textContent='本地链路验证';if(!send('start_proxy_task',{fileName,fileContent:text,fallbackPort:Number($('fallbackPort').value||443),sni,host:$('host').value.trim(),path:$('path').value.trim()||'/cdn-cgi/trace',enableTLS:tls,mode,threads:Number($('threads').value||0),timeoutMs:Number($('timeoutMs').value||0),insecure,speedLimit:mode==='precise'?10:0})){finishRun();return}"
if old_start not in html and new_start not in html:
    raise SystemExit('start button send block not found')
html = html.replace(old_start, new_start, 1)
index_path.write_text(html, encoding='utf-8')

readme_path = root / 'README.md'
readme = readme_path.read_text(encoding='utf-8')
needle = '默认本地 Web 地址沿用后端监听端口 `13335`。\n'
replacement = '默认本地 Web 地址为 `http://127.0.0.1:13335`，程序默认只监听本机回环地址，不会直接暴露到局域网或公网。\n'
if needle in readme:
    readme = readme.replace(needle, replacement, 1)
readme_path.write_text(readme, encoding='utf-8')

# Extend local-only regression tests with static UI safety assertions.
# Keep the test itself generic so no user-specific value is ever committed into product source.
test_path = go / 'proxy_local_integration_test.go'
test = test_path.read_text(encoding='utf-8')
if 'TestProxyLocalUIHasSafeDefaults' not in test:
    test += r'''

func TestProxyLocalUIHasSafeDefaults(t *testing.T) {
    data, err := staticFiles.ReadFile("index.html")
    if err != nil {
        t.Fatal(err)
    }
    html := string(data)
    required := []string{"ProxyIP Optimizer", "start_proxy_task", "example.com", "Host 默认跟随 SNI"}
    for _, item := range required {
        if !strings.Contains(html, item) {
            t.Fatalf("UI missing required marker %q", item)
        }
    }
    if strings.Contains(html, "value=\"example.com\"") {
        t.Fatal("SNI example must remain a placeholder, not a persisted default value")
    }
}
'''
    test_path.write_text(test, encoding='utf-8')

print('Local-only bind + UI resilience patch applied')
