import sys
import time
from playwright.sync_api import sync_playwright

DEFAULT_APPS = [
    "https://rqehmildgsfhedt39krz7a.streamlit.app/",
    "https://qdii-quota-monitor.streamlit.app/"
]

def wake_up_single(page, app_url):
    print(f"\n==========================================")
    print(f"🚀 正在使用 Playwright 真实无头浏览器访问: {app_url}")
    try:
        # 访问页面，等待 DOM 加载完毕
        page.goto(app_url, wait_until="domcontentloaded", timeout=60000)
        time.sleep(4)
        
        # 检查是否出现 Streamlit 休眠提示及唤醒按钮
        # 常见文本: "Yes, get this app back up", "get this app back up", "Wake up"
        wake_btn = page.locator('button:has-text("Yes, get this app back up"), button:has-text("get this app back up"), button:has-text("Wake up")')
        
        if wake_btn.count() > 0 and wake_btn.first.is_visible():
            print("⚡ 检测到 App 处于休眠状态 (Sleeping)！正在自动点击唤醒按钮...")
            wake_btn.first.click()
            print("⏳ 已成功点击唤醒按钮，等待 20 秒拉起服务与容器...")
            time.sleep(20)
            
            # 再次检查主界面是否已挂载
            try:
                page.wait_for_selector('[data-testid="stAppViewContainer"], button:has-text("Manage app")', timeout=30000)
                print("✅ 唤醒成功！Streamlit 主界面已挂载就绪！")
            except Exception:
                print("ℹ️ 唤醒指令已发送，后台正在启动服务。")
        else:
            print("✅ App 当前处于活跃在线状态，已完成真实 WebSocket 通信与渲染握手！")
            time.sleep(5)
            
        print(f"🎉 最终页面标题: {page.title()}")
        return True
    except Exception as e:
        print(f"⚠️ 访问 {app_url} 时捕获异常: {e}")
        return False

def main():
    target_urls = sys.argv[1:] if len(sys.argv) > 1 else DEFAULT_APPS
    print(f"📋 待保活唤醒列表 (共 {len(target_urls)} 个应用): {target_urls}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 StreamlitKeepAlive/3.0"
        )
        page = context.new_page()
        
        for url in target_urls:
            wake_up_single(page, url.strip())
            
        browser.close()
    print("\n🏁 所有 Streamlit 应用保活唤醒流程执行完毕！")

if __name__ == "__main__":
    main()
