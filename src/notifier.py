"""桌面通知 — 扫描完成时弹窗提醒。"""

import subprocess


def desktop_done(found_count: int) -> None:
    """扫描完成时弹出 Windows 通知。"""
    body = f"已发现 {found_count} 只基金接近1年低点，打开 data/扫描结果.txt 查看详情。"
    ps = f'''
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    $tpl = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
    $tpl.GetElementsByTagName("text")[0].AppendChild($tpl.CreateTextNode('全场基金扫描完成')) | Out-Null
    $tpl.GetElementsByTagName("text")[1].AppendChild($tpl.CreateTextNode('{body}')) | Out-Null
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('全场基金监测').Show([Windows.UI.Notifications.ToastNotification]::new($tpl))
    '''
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], timeout=15, capture_output=True, check=False)
    except Exception:
        pass
