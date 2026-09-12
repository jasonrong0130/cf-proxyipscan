//go:build windows

package main

import (
	"errors"
	"net/http"
	"os"
	"path/filepath"
	"time"
	"unsafe"

	webview2 "github.com/jchv/go-webview2"
	"golang.org/x/sys/windows"
)

func defaultDesktopMode() bool { return true }

func runDesktopWindow(displayURL string) error {
	if err := waitForDesktopServer(displayURL); err != nil {
		showDesktopError("CF优选IP筛选器", "本地服务启动失败："+err.Error())
		return err
	}

	enablePerMonitorDPI()
	windowWidth, windowHeight := preferredDesktopSize()

	dataPath := filepath.Join(os.Getenv("LOCALAPPDATA"), "CFIPSelector", "WebView2")
	if os.Getenv("LOCALAPPDATA") == "" {
		dataPath = filepath.Join(os.TempDir(), "CFIPSelector-WebView2")
	}
	_ = os.MkdirAll(dataPath, 0o755)

	w := webview2.NewWithOptions(webview2.WebViewOptions{
		Debug:     debugMode,
		AutoFocus: true,
		DataPath:  dataPath,
		WindowOptions: webview2.WindowOptions{
			Title:  "CF优选IP筛选器",
			Width:  uint(windowWidth),
			Height: uint(windowHeight),
			Center: true,
		},
	})
	if w == nil {
		showDesktopError("CF优选IP筛选器", "无法启动桌面窗口。请确认 Microsoft Edge WebView2 Runtime 已安装。")
		return errors.New("无法创建 WebView2 桌面窗口")
	}
	defer w.Destroy()

	w.SetSize(1060, 700, webview2.HintMin)
	w.SetSize(windowWidth, windowHeight, webview2.HintNone)
	w.Init(desktopLayoutScript())
	w.Navigate(displayURL)
	w.Run()
	return nil
}

func preferredDesktopSize() (int, int) {
	user32 := windows.NewLazySystemDLL("user32.dll")
	getSystemMetrics := user32.NewProc("GetSystemMetrics")
	widthRaw, _, _ := getSystemMetrics.Call(0)
	heightRaw, _, _ := getSystemMetrics.Call(1)
	width, height := int(widthRaw), int(heightRaw)
	if width <= 0 || height <= 0 {
		return 1360, 860
	}

	windowWidth := width * 80 / 100
	windowHeight := height * 90 / 100
	return clampDesktop(windowWidth, 1100, 1580), clampDesktop(windowHeight, 720, 980)
}

func clampDesktop(v, minV, maxV int) int {
	if v < minV {
		return minV
	}
	if v > maxV {
		return maxV
	}
	return v
}

func desktopLayoutScript() string {
	return `(function(){
const apply=function(){
  if(document.getElementById('desktop-layout-style')) return;
  const style=document.createElement('style');
  style.id='desktop-layout-style';
  style.textContent='\
html,body{height:100%!important;min-height:0!important;overflow:hidden!important}\
body{padding:7px!important}\
.shell{height:calc(100vh - 14px)!important;max-height:calc(100vh - 14px)!important;width:100%!important;display:flex!important;flex-direction:column!important;overflow:hidden!important}\
.titlebar{height:50px!important;min-height:50px!important;padding:0 15px!important;flex:0 0 50px!important}\
.brandmark{width:32px!important;height:32px!important;border-radius:10px!important;font-size:17px!important}.brand b{font-size:16px!important}.brand span{font-size:10px!important}\
.main{padding:8px 13px 8px!important;flex:1 1 auto!important;min-height:0!important;display:flex!important;flex-direction:column!important;overflow:hidden!important}\
.hero{margin-bottom:5px!important;flex:0 0 auto!important}.hero h1{font-size:21px!important;margin:0 0 1px!important}.hero p{font-size:10px!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important}\
.stats{gap:7px!important;margin-bottom:6px!important;flex:0 0 auto!important}.stat{padding:6px 11px!important;gap:8px!important}.stat .ico{width:31px!important;height:31px!important;font-size:16px!important}.stat strong{font-size:18px!important}.stat label{font-size:10px!important}\
.twocol{gap:7px!important;flex:0 0 auto!important}.card{padding:8px 10px!important}.cardhead{font-size:13px!important;margin-bottom:5px!important}.dropgrid{gap:7px!important}.dropzone{min-height:78px!important}.preview{max-height:78px!important;padding:7px!important}.actions{margin-top:5px!important}.btn,.ghost{padding:6px 9px!important}.formrow{grid-template-columns:70px 1fr!important;gap:6px!important;margin-bottom:4px!important}.input,select{height:30px!important}.note{margin-top:2px!important;line-height:1.2!important;font-size:10px!important}\
.desktop-advanced-strip{margin:6px 0 0!important;padding:6px 8px!important;display:grid!important;grid-template-columns:72px minmax(145px,1.25fr) minmax(275px,2.35fr) 72px 66px 76px 92px 92px 72px!important;gap:7px!important;align-items:end!important;background:var(--glass)!important;border:1px solid rgba(255,255,255,.82)!important;box-shadow:var(--shadow)!important;backdrop-filter:blur(8px) saturate(135%)!important;border-radius:var(--radius)!important;flex:0 0 auto!important;min-height:52px!important}\
.desktop-advanced-title{align-self:center!important;font-size:11px!important;font-weight:800!important;color:#44536a!important;white-space:nowrap!important}.desktop-advanced-strip>.formrow{display:flex!important;flex-direction:column!important;gap:3px!important;margin:0!important;min-width:0!important}.desktop-advanced-strip .formrow label{font-size:9px!important;line-height:1!important;white-space:nowrap!important}.desktop-advanced-strip .input{height:27px!important;padding:0 7px!important;font-size:10px!important}.desktop-advanced-strip .switchrow{height:27px!important;gap:4px!important;font-size:10px!important}.desktop-advanced-strip .switch{transform:scale(.78);transform-origin:left center;margin-right:-7px!important}\
.desktop-advanced-strip .portchoices{height:27px!important;min-height:27px!important;gap:2px!important;flex-wrap:nowrap!important;overflow:hidden!important}.desktop-advanced-strip .portchoice{padding:3px 4px!important;border-radius:6px!important;font-size:9px!important;gap:2px!important}.desktop-advanced-strip .portchoice input{width:11px!important;height:11px!important}\
.runbar{padding:6px 10px!important;margin-top:6px!important;flex:0 0 auto!important}.runbar .run-title{font-size:12px!important}.runbar .run-note{font-size:9px!important}.progresscard{padding:5px 10px!important;margin-top:5px!important;gap:8px!important;flex:0 0 auto!important}.ring{width:24px!important;height:24px!important;border-width:4px!important}.progressmeta{width:195px!important}.progressmeta b{font-size:11px!important}.progressmeta span{font-size:9px!important}.track{height:6px!important}\
.results{margin-top:6px!important;padding:7px 9px 6px!important;flex:1 1 auto!important;min-height:0!important;display:flex!important;flex-direction:column!important;overflow:hidden!important}.result-title{margin-bottom:4px!important;flex:0 0 auto!important}.result-title b{font-size:13px!important}.filters{gap:4px!important;margin-bottom:4px!important;flex:0 0 auto!important}.filters .input,.filters select{height:28px!important;font-size:10px!important}.filterhint{font-size:9px!important}.result-actions{gap:4px!important;padding:4px 0!important;flex:0 0 auto!important}.scope{height:28px!important;font-size:10px!important}.mini{padding:4px 7px!important;font-size:10px!important}.tablewrap{margin-top:4px!important;max-height:none!important;min-height:120px!important;flex:1 1 auto!important;overflow:auto!important}.pager{margin-top:4px!important;flex:0 0 auto!important}.pager select{height:27px!important}th,td{padding:5px 7px!important;font-size:10px!important}th{font-size:9px!important}\
@media(max-width:1180px){.topnav{display:flex!important}.stats{grid-template-columns:repeat(4,1fr)!important}.twocol{grid-template-columns:1.05fr 1fr!important}.filterhint{display:none!important}.desktop-advanced-strip{grid-template-columns:62px minmax(125px,1.1fr) minmax(235px,2fr) repeat(6,minmax(62px,1fr))!important}}';
  document.head.appendChild(style);

  const adv=document.getElementById('advanced');
  const two=document.querySelector('.twocol');
  if(adv&&two){
    const strip=document.createElement('section');
    strip.id='advanced';
    strip.className='glass desktop-advanced-strip';

    const title=document.createElement('div');
    title.className='desktop-advanced-title';
    title.textContent='⚙ 高级设置';
    strip.appendChild(title);

    Array.from(adv.querySelectorAll(':scope > .formrow')).forEach(function(row){
      strip.appendChild(row);
    });

    two.insertAdjacentElement('afterend',strip);
    adv.remove();
  }
};
if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',apply); else apply();
})();`
}

func waitForDesktopServer(displayURL string) error {
	client := &http.Client{Timeout: 500 * time.Millisecond}
	deadline := time.Now().Add(4 * time.Second)
	var lastErr error
	for time.Now().Before(deadline) {
		resp, err := client.Get(displayURL)
		if err == nil {
			_ = resp.Body.Close()
			return nil
		}
		lastErr = err
		time.Sleep(100 * time.Millisecond)
	}
	if lastErr == nil {
		lastErr = errors.New("等待本地服务超时")
	}
	return lastErr
}

func enablePerMonitorDPI() {
	user32 := windows.NewLazySystemDLL("user32.dll")
	setDPIContext := user32.NewProc("SetProcessDpiAwarenessContext")
	if err := setDPIContext.Find(); err == nil {
		ret, _, _ := setDPIContext.Call(uintptr(^uintptr(3)))
		if ret != 0 {
			return
		}
	}
	setProcessDPIAware := user32.NewProc("SetProcessDPIAware")
	if err := setProcessDPIAware.Find(); err == nil {
		_, _, _ = setProcessDPIAware.Call()
	}
}

func showDesktopError(title, message string) {
	user32 := windows.NewLazySystemDLL("user32.dll")
	messageBoxW := user32.NewProc("MessageBoxW")
	titlePtr, _ := windows.UTF16PtrFromString(title)
	messagePtr, _ := windows.UTF16PtrFromString(message)
	const mbIconError = 0x00000010
	const mbOK = 0x00000000
	_, _, _ = messageBoxW.Call(0, uintptr(unsafe.Pointer(messagePtr)), uintptr(unsafe.Pointer(titlePtr)), mbOK|mbIconError)
}
