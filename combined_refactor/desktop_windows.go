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
	// 桌面模式不向用户保留控制台窗口；错误通过 MessageBox 呈现。
	hideConsoleWindow()

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

	// 每次启动使用独立 profile，避免 Edge/Chrome 的单实例锁、残留后台进程或旧 profile
	// 导致 --app 请求被吞掉、主程序一直等待但窗口不出现。
	dataPath, err := os.MkdirTemp("", "CFIPSelector-"+browserName+"App-")
	if err != nil {
		showDesktopError("CF优选IP筛选器", "无法创建桌面运行目录："+err.Error())
		return err
	}
	defer os.RemoveAll(dataPath)

	args := []string{
		"--app=" + displayURL,
		"--user-data-dir=" + dataPath,
		"--no-first-run",
		"--no-default-browser-check",
		"--disable-background-mode",
		"--disable-features=msEdgeSidebarV2",
		"--window-size=1160,760",
		"--force-color-profile=srgb",
	}
	cmd := exec.Command(browserPath, args...)
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
	if err := cmd.Start(); err != nil {
		showDesktopError("CF优选IP筛选器", "桌面窗口启动失败："+err.Error())
		return err
	}

	// 独立 profile 下该进程对应本次 App 生命周期；窗口关闭后 Wait 返回，
	// 主程序随后关闭本地 HTTP 服务，不残留后台端口。
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

func hideConsoleWindow() {
	kernel32 := windows.NewLazySystemDLL("kernel32.dll")
	user32 := windows.NewLazySystemDLL("user32.dll")
	getConsoleWindow := kernel32.NewProc("GetConsoleWindow")
	showWindow := user32.NewProc("ShowWindow")
	hwnd, _, _ := getConsoleWindow.Call()
	if hwnd != 0 {
		const swHide = 0
		_, _, _ = showWindow.Call(hwnd, swHide)
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
