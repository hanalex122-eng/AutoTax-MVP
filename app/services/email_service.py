"""
AutoTax.cloud — E-posta Servisi
SMTP (Gmail / SendGrid / Mailgun) desteği.
ENV değişkenleri:
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM
"""
import os
import smtplib
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text      import MIMEText
from datetime             import datetime
from typing               import Optional

_SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
_SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
_SMTP_USER = os.getenv("SMTP_USER", "")
_SMTP_PASS = os.getenv("SMTP_PASS", "")
_SMTP_FROM = os.getenv("SMTP_FROM", _SMTP_USER)
_APP_URL   = os.getenv("APP_URL", "https://autotax.cloud")

_CONFIGURED = bool(_SMTP_USER and _SMTP_PASS)


def _send(to: str, subject: str, html: str, text: str = "") -> bool:
    if not _CONFIGURED:
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"AutoTax.cloud <{_SMTP_FROM}>"
        msg["To"]      = to
        if text:
            msg.attach(MIMEText(text, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))
        with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=15) as s:
            s.starttls()
            s.login(_SMTP_USER, _SMTP_PASS)
            s.sendmail(_SMTP_FROM, [to], msg.as_bytes())
        return True
    except Exception:
        return False


def send_async(to: str, subject: str, html: str, text: str = "") -> None:
    """E-postayı arka planda gönder (isteği bloklamaz)."""
    threading.Thread(target=_send, args=(to, subject, html, text), daemon=True).start()


# ── Şablonlar ─────────────────────────────────────────────────────────────────

def _base(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  body   {{ font-family: system-ui,sans-serif; background:#f0f4ff; margin:0; padding:24px; }}
  .card  {{ background:#fff; border-radius:12px; max-width:560px; margin:0 auto;
            padding:32px; box-shadow:0 2px 12px rgba(0,0,0,.08); }}
  .logo  {{ font-size:22px; font-weight:700; color:#2563eb; margin-bottom:24px; }}
  h2     {{ font-size:20px; color:#1e293b; margin:0 0 12px; }}
  p      {{ color:#475569; line-height:1.6; margin:8px 0; }}
  .btn   {{ display:inline-block; margin:20px 0; padding:12px 28px;
            background:#2563eb; color:#fff; border-radius:99px;
            text-decoration:none; font-weight:600; font-size:15px; }}
  .stat  {{ background:#f8faff; border-radius:8px; padding:12px 16px; margin:8px 0; }}
  .stat strong {{ color:#2563eb; font-size:20px; }}
  small  {{ color:#94a3b8; font-size:12px; }}
  hr     {{ border:none; border-top:1px solid #e2e8f0; margin:20px 0; }}
</style>
</head>
<body>
<div class="card">
  <div class="logo">AutoTax.cloud</div>
  <h2>{title}</h2>
  {body}
  <hr>
  <small>AutoTax.cloud — Akıllı Fatura Yönetimi &bull;
         <a href="{_APP_URL}/unsubscribe" style="color:#94a3b8">Aboneliği iptal et</a></small>
</div>
</body>
</html>"""


def send_welcome(to: str, name: str) -> None:
    body = f"""
    <p>Merhaba <strong>{name}</strong>,</p>
    <p>AutoTax.cloud'a hoş geldiniz! Faturalarınızı OCR ile otomatik okuyabilir,
       analiz edebilir ve muhasebe raporları oluşturabilirsiniz.</p>
    <a class="btn" href="{_APP_URL}/app">Uygulamayı Aç</a>
    <p>Sorularınız için destek ekibimiz her zaman hazır.</p>"""
    send_async(to, "AutoTax.cloud'a Hoş Geldiniz!", _base("Hoş Geldiniz!", body))


def send_quota_warning(to: str, name: str, used: int, limit: int, plan: str) -> None:
    pct  = int(used / limit * 100)
    body = f"""
    <p>Merhaba <strong>{name}</strong>,</p>
    <p>Bu ay fatura kotanızın <strong>%{pct}'ini</strong> kullandınız.</p>
    <div class="stat">Kullanım: <strong>{used}</strong> / {limit} fatura</div>
    <p>Limitinize yaklaşıyorsunuz. Plan yükselterek sınırsız fatura işleyebilirsiniz.</p>
    <a class="btn" href="{_APP_URL}/landing.html#pricing">Planları Gör</a>"""
    send_async(to, f"Fatura kotanızın %{pct}'i doldu — AutoTax.cloud", _base("Kota Uyarısı", body))


def send_monthly_summary(to: str, name: str, stats: dict) -> None:
    month    = datetime.now().strftime("%B %Y")
    income   = stats.get("income",  0)
    expense  = stats.get("expense", 0)
    net      = income - expense
    count    = stats.get("count",   0)
    net_sign = "+" if net >= 0 else ""
    body = f"""
    <p>Merhaba <strong>{name}</strong>,</p>
    <p><strong>{month}</strong> ayı fatura özetiniz hazır:</p>
    <div class="stat">Toplam Fatura: <strong>{count}</strong></div>
    <div class="stat">Gelir: <strong style="color:#16a34a">€{income:,.2f}</strong></div>
    <div class="stat">Gider: <strong style="color:#dc2626">€{expense:,.2f}</strong></div>
    <div class="stat">Net Bakiye: <strong style="color:{'#16a34a' if net>=0 else '#dc2626'}">{net_sign}€{net:,.2f}</strong></div>
    <a class="btn" href="{_APP_URL}/app">Detaylı Raporu Gör</a>"""
    send_async(to, f"{month} Aylık Özet — AutoTax.cloud", _base(f"{month} Özeti", body))


def send_duplicate_warning(to: str, name: str, vendor: str, amount: float, orig_date: str) -> None:
    body = f"""
    <p>Merhaba <strong>{name}</strong>,</p>
    <p>Az önce yüklediğiniz fatura daha önce sisteme eklenmiş olabilir:</p>
    <div class="stat">
      Firma: <strong>{vendor}</strong><br>
      Tutar: <strong>€{amount:,.2f}</strong><br>
      İlk Yükleme: <strong>{orig_date}</strong>
    </div>
    <p>Lütfen faturalarınızı kontrol edin. Duplikasyon ise silebilirsiniz.</p>
    <a class="btn" href="{_APP_URL}/app">Faturalara Git</a>"""
    send_async(to, "Duplik Fatura Uyarısı — AutoTax.cloud", _base("Duplik Fatura Tespit Edildi", body))


def send_family_invite(to: str, inviter_name: str, invite_link: str) -> None:
    body = f"""
    <p><strong>{inviter_name}</strong> sizi AutoTax.cloud Aile planına davet etti.</p>
    <p>Daveti kabul ederek fatura yönetimini paylaşabilirsiniz.</p>
    <a class="btn" href="{invite_link}">Daveti Kabul Et</a>
    <p><small>Bu davet 7 gün geçerlidir.</small></p>"""
    send_async(to, f"{inviter_name} sizi AutoTax.cloud'a davet etti", _base("Aile Planı Daveti", body))


def send_password_reset(to: str, reset_link: str) -> bool:
    body = f"""
    <p>Merhaba,</p>
    <p>AutoTax.cloud hesabınız için şifre sıfırlama talebinde bulundunuz.</p>
    <a class="btn" href="{reset_link}">Şifremi Sıfırla</a>
    <p><small>Bu bağlantı <strong>2 saat</strong> geçerlidir. Talebi siz yapmadıysanız bu e-postayı görmezden gelebilirsiniz.</small></p>"""
    return _send(to, "Şifre Sıfırlama — AutoTax.cloud", _base("Şifre Sıfırlama", body))

