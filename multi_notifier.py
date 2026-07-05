import os
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_serverchan(title: str, content: str):
    """
    通过 Server酱 发送推送通知
    """
    sendkey = os.environ.get("SERVERCHAN_SENDKEY")
    if not sendkey:
        return

    url = f"https://sctapi.ftqq.com/{sendkey}.send"
    data = {
        "title": title,
        "desp": content
    }
    
    try:
        response = requests.post(url, data=data, timeout=10)
        response.raise_for_status()
        result = response.json()
        if result.get("code") == 0:
            print("✅ Server酱推送成功")
        else:
            print(f"❌ Server酱推送失败，API返回: {result}")
    except Exception as e:
        print(f"❌ Server酱推送请求异常: {e}")

def send_qq_email(title: str, content: str):
    """
    通过 QQ邮箱 SMTP 发送推送通知
    """
    smtp_user = os.environ.get("QQ_SMTP_USER")
    smtp_pass = os.environ.get("QQ_SMTP_PASS")
    # 如果没有单独配置接收邮箱，则默认发给自己（发件人=收件人）
    receiver = os.environ.get("RECEIVER_EMAIL", smtp_user)

    if not smtp_user or not smtp_pass:
        return

    # 构建邮件内容 (此处使用 plain 纯文本模式，如果是 Markdown 格式可以通过转换库转为 HTML)
    msg = MIMEMultipart()
    msg['From'] = smtp_user
    msg['To'] = receiver
    msg['Subject'] = title
    
    # 注入正文
    msg.attach(MIMEText(content, 'plain', 'utf-8'))

    try:
        # QQ邮箱的 SMTP SSL 端口为 465
        server = smtplib.SMTP_SSL("smtp.qq.com", 465)
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, receiver, msg.as_string())
        server.quit()
        print("✅ QQ邮箱推送成功")
    except Exception as e:
        print(f"❌ QQ邮箱推送失败: {e}")

def push_all(title: str, content: str):
    """
    触发所有已配置的推送方式
    """
    send_serverchan(title, content)
    send_qq_email(title, content)
