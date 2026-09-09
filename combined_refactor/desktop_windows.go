//go:build windows

package main

import (
	"errors"
	"fmt"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"syscall"
	"time"
	"unsafe"

	"golang.org/x/sys/windows"
)

func defaultDesktopMode() bool { return true }

func runDesktopWindow(displayURL string) error {
	if err := waitForDesktopServer(displayURL); err != nil {
		showDesktopError("CF优选IP筛选器", "本地服务启动失败："+err.Error())
		return err
	}

	browserPath, browserName := findDesktopBrowser()
	if browserPath == "" {
		err := errors.New("未找到 Microsoft Edge 或 Google Chrome")
		showDesktopError("CF优选IP筛选器", "无法启动桌面窗口。请确认 Microsoft Edge 已安装。")
		return err
	}

	dataPath := filepath.Join(os.Getenv("LOCALAPPDATA"), "CFIPSelector", browserName+"App")
	if os.Getenv("LOCALAPPDATA") == "" {
		dataPath = filepath.Join(os.TempDir(), "CFIPSelector-"+browserName+"App")
	}
	_ = os.MkdirAll(dataPath, 0o755)

	args := []string{
		"--app=" + displayURL,
		"--user-data-dir=" + dataPath,
		"--no-first-run",
		"--no-default-browser-check",
		"--disable-background-mode",
		// 桌面版使用更紧凑的默认窗口；避免高分屏下被 Windows 150%/175% 缩放得过大。
		"--window-size=1160,760",
		"--high-dpi-support=1",
		"--force-device-scale-factor=1",
		"--force-color-profile=srgb",
	}
	cmd := exec.Command(browserPath, args...)
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
	if err := cmd.Start(); err != nil {
		showDesktopError("CF优选IP筛选器", "桌面窗口启动失败："+err.Error())
		return err
	}

	// 使用独立 user-data-dir，浏览器会维持一个独立的 App 进程组。
	// 用户关闭 App 窗口后 Wait 返回，主程序随后关闭本地 HTTP 服务。
	if err := cmd.Wait(); err != nil {
		return fmt.Errorf("%s 桌面窗口异常退出: %w", browserName, err)
	}
	return nil
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

func findDesktopBrowser() (string, string) {
	candidates := []struct {
		path string
		name string
	}{
		{filepath.Join(os.Getenv("ProgramFiles(x86)"), "Microsoft", "Edge", "Application", "msedge.exe"), "Edge"},
		{filepath.Join(os.Getenv("ProgramFiles"), "Microsoft", "Edge", "Application", "msedge.exe"), "Edge"},
		{filepath.Join(os.Getenv("LOCALAPPDATA"), "Microsoft", "Edge", "Application", "msedge.exe"), "Edge"},
		{filepath.Join(os.Getenv("ProgramFiles"), "Google", "Chrome", "Application", "chrome.exe"), "Chrome"},
		{filepath.Join(os.Getenv("ProgramFiles(x86)"), "Google", "Chrome", "Application", "chrome.exe"), "Chrome"},
		{filepath.Join(os.Getenv("LOCALAPPDATA"), "Google", "Chrome", "Application", "chrome.exe"), "Chrome"},
	}
	for _, candidate := range candidates {
		if candidate.path == "" {
			continue
		}
		if info, err := os.Stat(candidate.path); err == nil && !info.IsDir() {
			return candidate.path, candidate.name
		}
	}
	if path, err := exec.LookPath("msedge.exe"); err == nil {
		return path, "Edge"
	}
	if path, err := exec.LookPath("chrome.exe"); err == nil {
		return path, "Chrome"
	}
	return "", ""
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
