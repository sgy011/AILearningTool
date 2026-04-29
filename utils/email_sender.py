from __future__ import annotations

import os
import smtplib
import socket
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def send_qq_email(*, to_email: str, subject: str, content: str) -> None:
    host = (os.getenv("QQ_SMTP_HOST") or "smtp.qq.com").strip()
    port = int(os.getenv("QQ_SMTP_PORT") or "465")
    sender = (os.getenv("QQ_SMTP_SENDER") or "").strip()
    password = (os.getenv("QQ_SMTP_PASSWORD") or "").strip()
    if (password.startswith('"') and password.endswith('"')) or (
        password.startswith("'") and password.endswith("'")
    ):
        password = password[1:-1].strip()
    if not sender or not password:
        raise RuntimeError("未配置 QQ SMTP 发件人/授权码（QQ_SMTP_SENDER/QQ_SMTP_PASSWORD）")

    recivers = (to_email or "").strip()
    if not recivers:
        raise RuntimeError("收件人邮箱为空")

    message = MIMEMultipart()
    msg = MIMEText(content or "", "plain", "utf-8")
    message.attach(msg)
    message["From"] = sender
    message["To"] = recivers
    message["Subject"] = subject or "邮箱验证"

    timeout = float(os.getenv("QQ_SMTP_TIMEOUT_SEC") or "20")

    # 宽松 SSL context，兼容更多环境
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    errors: list[Exception] = []

    # 方案 1：465 端口 + SMTP_SSL（主要方案）
    if port == 465:
        try:
            with smtplib.SMTP_SSL(host, port, timeout=timeout, context=ctx) as smtp:
                smtp.login(sender, password)
                smtp.sendmail(sender, recivers, message.as_string())
            return
        except smtplib.SMTPAuthenticationError:
            raise  # 鉴权失败直接抛出，不尝试其他方案
        except Exception as e:
            errors.append(e)

    # 方案 2：587 端口 + STARTTLS
    if port == 587:
        try:
            with smtplib.SMTP(host, port, timeout=timeout) as smtp:
                smtp.ehlo()
                smtp.starttls(context=ctx)
                smtp.ehlo()
                smtp.login(sender, password)
                smtp.sendmail(sender, recivers, message.as_string())
            return
        except smtplib.SMTPAuthenticationError:
            raise
        except Exception as e:
            errors.append(e)

    # 方案 3：其他端口先试 SSL 再试 STARTTLS
    try:
        with smtplib.SMTP_SSL(host, port, timeout=timeout, context=ctx) as smtp:
            smtp.login(sender, password)
            smtp.sendmail(sender, recivers, message.as_string())
        return
    except smtplib.SMTPAuthenticationError:
        raise
    except Exception as e:
        errors.append(e)

    try:
        with smtplib.SMTP(host, port, timeout=timeout) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ctx)
            smtp.ehlo()
            smtp.login(sender, password)
            smtp.sendmail(sender, recivers, message.as_string())
        return
    except smtplib.SMTPAuthenticationError:
        raise
    except Exception as e:
        errors.append(e)

    # 所有方案均失败
    detail = "; ".join(f"{type(e).__name__}: {e}" for e in errors)
    raise RuntimeError(
        f"发送邮件失败（已尝试多种连接方式）：{detail}\n"
        f"当前配置：host={host}, port={port}, sender={sender}\n"
        "请检查：1) QQ邮箱已开启SMTP服务  2) 使用最新授权码  3) 网络/防火墙未拦截"
    )
