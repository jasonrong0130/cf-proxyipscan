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
	widthRaw, _, _ := getSystemMetrics.Call(0)  // SM_CXSCREEN
	heightRaw, _, _ := getSystemMetrics.Call(1) // SM_CYSCREEN
	width, height := int(widthRaw), int(heightRaw)
	if width <= 0 || height <= 0 {
		return 1360, 860
	}

	// 与用户目标截图接近：左右保留桌面边距，高度接近完整工作区。
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
body{padding:8px!important}\
.shell{height:calc(100vh - 16px)!important;max-height:calc(100vh - 16px)!important;width:100%!important;display:flex!important;flex-direction:column!important;overflow:hidden!important}\
.titlebar{height:54px!important;min-height:54px!important;padding:0 16px!important;flex:0 0 54px!important}\
.brandmark{width:34px!important;height:34px!important;border-radius:11px!important;font-size:18px!important}.brand b{font-size:17px!important}\
.main{padding:11px 15px 10px!important;flex:1 1 auto!important;min-height:0!important;display:flex!important;flex-direction:column!important;overflow:hidden!important}\
.hero{margin-bottom:7px!important;flex:0 0 auto!important}.hero h1{font-size:23px!important;margin:0 0 2px!important}.hero p{font-size:11px!important}\
.stats{gap:8px!important;margin-bottom:7px!important;flex:0 0 auto!important}.stat{padding:8px 13px!important;gap:9px!important}.stat .ico{width:35px!important;height:35px!important;font-size:17px!important}.stat strong{font-size:20px!important}.stat label{font-size:11px!important}\
.twocol{gap:8px!important;flex:0 0 auto!important}.card{padding:10px 12px!important}.cardhead{font-size:14px!important;margin-bottom:7px!important}.dropgrid{gap:8px!important}.dropzone{min-height:92px!important}.preview{max-height:92px!important;padding:8px!important}.actions{margin-top:6px!important}.btn,.ghost{padding:7px 10px!important}.formrow{grid-template-columns:78px 1fr!important;gap:7px!important;margin-bottom:5px!important}.input,select{height:32px!important}.note{margin-top:3px!important;line-height:1.3!important}\
details.desktop-advanced-strip{margin:7px 0 0!important;padding:7px 10px 8px!important;display:grid!important;grid-template-columns:1.7fr .85fr .85fr .85fr 1fr .9fr .85fr!important;gap:5px 8px!important;align-items:end!important;background:var(--glass)!important;border:1px solid rgba(255,255,255,.82)!important;box-shadow:var(--shadow)!important;backdrop-filter:blur(8px) saturate(135%)!important;border-radius:var(--radius)!important;flex:0 0 auto!important}\
details.desktop-advanced-strip>summary{grid-column:1/-1!important;list-style:none!important;cursor:default!important;font-size:12px!important;font-weight:800!important;color:#44536a!important;margin:0 0 1px!important}details.desktop-advanced-strip>summary::-webkit-details-marker{display:none!important}\
details.desktop-advanced-strip>.formrow{display:flex!important;flex-direction:column!important;gap:3px!important;margin:0!important;min-width:0!important}.desktop-advanced-strip .formrow label{font-size:10px!important;line-height:1!important;white-space:nowrap!important}.desktop-advanced-strip .input{height:29px!important;padding:0 8px!important;font-size:11px!important}.desktop-advanced-strip .switchrow{height:29px!important}.desktop-advanced-strip .switch{transform:scale(.88);transform-origin:left center}.desktop-advanced-strip .note{display:none!important}\
.runbar{padding:7px 11px!important;margin-top:7px!important;flex:0 0 auto!important}.runbar .run-note{font-size:10px!important}.progresscard{padding:6px 11px!important;margin-top:6px!important;gap:10px!important;flex:0 0 auto!important}.ring{width:27px!important;height:27px!important;border-width:4px!important}.progressmeta{width:220px!important}.track{height:7px!important}\
.results{margin-top:7px!important;padding:8px 10px 7px!important;flex:1 1 auto!important;min-height:0!important;display:flex!important;flex-direction:column!important;overflow:hidden!important}.result-title{margin-bottom:5px!important;flex:0 0 auto!important}.result-title b{font-size:14px!important}.filters{gap:5px!important;margin-bottom:5px!important;flex:0 0 auto!important}.filters .input,.filters select{height:30px!important}.filterhint{font-size:10px!important}.result-actions{gap:5px!important;padding:5px 0!important;flex:0 0 auto!important}.scope{height:30px!important}.mini{padding:5px 8px!important}.tablewrap{margin-top:5px!important;max-height:none!important;min-height:110px!important;flex:1 1 auto!important;overflow:auto!important}.pager{margin-top:5px!important;flex:0 0 auto!important}.pager select{height:29px!important}th,td{padding:6px 8px!important}\
@media(max-width:1150px){.topnav{display:flex!important}.stats{grid-template-columns:repeat(4,1fr)!important}.twocol{grid-template-columns:1.05fr 1fr!important}.filterhint{display:none!important}details.desktop-advanced-strip{grid-template-columns:1.5fr repeat(6,1fr)!important}}';
  document.head.appendChild(style);

  const adv=document.getElementById('advanced');
  const two=document.querySelector('.twocol');
  if(adv&&two){
    adv.open=true;
    adv.classList.add('desktop-advanced-strip');
    const spacer=adv.querySelector(':scope > div[style*="height"]');
    if(spacer) spacer.remove();
    two.insertAdjacentElement('afterend',adv);
    const summary=adv.querySelector('summary');
    if(summary) summary.textContent='⚙ 高级设置';
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
