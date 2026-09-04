"""
api/email_report.py — AI Revenue Recovery Engine
=================================================
Builds and sends the structured decision email report via Gmail SMTP.

Rules:
  • communication.message_body is passed verbatim from the caller — never
    generated, rewritten, or fabricated here.
  • SMTP credentials are read exclusively from environment variables
    (REPORT_EMAIL_HOST, REPORT_EMAIL_PORT, REPORT_EMAIL_USERNAME,
     REPORT_EMAIL_PASSWORD, REPORT_EMAIL_FROM).
  • The email explicitly states the Customer Message is included for
    reporting purposes only and was NOT sent to the customer.
"""

from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, Optional


# ─────────────────────────────────────────────────────────────────────────────
# SMTP CONFIGURATION  (env vars only — never hardcoded)
# ─────────────────────────────────────────────────────────────────────────────

def _smtp_config() -> Dict[str, Any]:
    return {
        "host":     os.environ.get("REPORT_EMAIL_HOST", "smtp.gmail.com"),
        "port":     int(os.environ.get("REPORT_EMAIL_PORT", "587")),
        "username": os.environ.get("REPORT_EMAIL_USERNAME", ""),
        "password": os.environ.get("REPORT_EMAIL_PASSWORD", ""),
        "from":     os.environ.get("REPORT_EMAIL_FROM", ""),
    }


# ─────────────────────────────────────────────────────────────────────────────
# EMAIL BUILDERS
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_nullable(value: Any, prefix: str = "", suffix: str = "") -> str:
    """Format a nullable numeric/string field; returns em-dash if None/empty."""
    if value is None or value == "":
        return "—"
    return f"{prefix}{value}{suffix}"


def build_plain_text(payload: Dict[str, Any]) -> str:
    comm = payload.get("communication", {})
    message_body: Optional[str] = comm.get("message_body") or None
    sendable: bool = bool(comm.get("sendable", False))
    channel: Optional[str] = comm.get("channel") or None
    fallback_used: bool = bool(comm.get("fallback_used", False))

    prob = payload.get("selected_probability")
    prob_display = f"{prob * 100:.2f}%" if prob is not None else "—"

    ev = payload.get("selected_ev")
    ev_display = f"₹{ev:.2f}" if ev is not None else "—"

    lines = [
        "AI Revenue Recovery Engine",
        "=" * 50,
        "REVENUE RECOVERY DECISION",
        "=" * 50,
        "",
        f"Transaction ID       : {payload.get('transaction_id', '—')}",
        f"Amount               : {_fmt_nullable(payload.get('amount'), prefix='₹')}",
        f"Failure Type         : {payload.get('failure_type', '—')}",
        f"Recommended Action   : {payload.get('selected_action', '—').upper()}",
        f"Decision Type        : {payload.get('decision_type', '—')}",
        f"Recovery Probability : {prob_display}",
        f"Expected Value       : {ev_display}",
        f"Escalation           : {'Required' if payload.get('escalation_required') else 'Not Required'}",
        f"Terminal             : {'Yes' if payload.get('terminal') else 'No'}",
        f"Trace ID             : {payload.get('trace_id') or '—'}",
        f"Policy Version       : {payload.get('policy_version', '—')}",
        "",
        "─" * 50,
        "CUSTOMER MESSAGE",
        "─" * 50,
        "(Included in this report for audit purposes only.",
        " This message was NOT delivered to the customer.)",
        "",
    ]

    if message_body:
        lines.append(message_body)
    else:
        lines.append("Not available — this action does not produce a customer message.")

    lines += [
        "",
        "─" * 50,
        "COMMUNICATION STATUS",
        f"  Sendable : {'Yes' if sendable else 'No'}",
        f"  Channel  : {channel.upper() if channel else '—'}",
        "",
        "FALLBACK STATUS",
        f"  {('Fallback Used' if fallback_used else 'Not Used')}",
        "",
        "─" * 50,
        "This report was generated automatically by the AI Revenue Recovery Engine.",
    ]

    return "\n".join(lines)


def build_html(payload: Dict[str, Any]) -> str:
    comm = payload.get("communication", {})
    message_body: Optional[str] = comm.get("message_body") or None
    sendable: bool = bool(comm.get("sendable", False))
    channel: Optional[str] = comm.get("channel") or None
    fallback_used: bool = bool(comm.get("fallback_used", False))

    prob = payload.get("selected_probability")
    prob_display = f"{prob * 100:.2f}%" if prob is not None else "—"

    ev = payload.get("selected_ev")
    ev_display = f"₹{ev:.2f}" if ev is not None else "—"

    txn_id      = payload.get("transaction_id", "—")
    amount      = payload.get("amount")
    failure     = payload.get("failure_type", "—")
    action      = (payload.get("selected_action") or "—").upper()
    dec_type    = payload.get("decision_type", "—")
    escalation  = "Required" if payload.get("escalation_required") else "Not Required"
    terminal    = "Yes" if payload.get("terminal") else "No"
    trace_id    = payload.get("trace_id") or "—"
    policy_ver  = payload.get("policy_version", "—")
    amount_disp = f"₹{amount:.2f}" if amount is not None else "—"

    comm_status_color = "#22c55e" if sendable else "#ef4444"
    comm_status_label = "Sendable · Active" if sendable else "Not Sendable"
    escalation_color  = "#ef4444" if escalation == "Required" else "#22c55e"
    terminal_color    = "#ef4444" if terminal == "Yes" else "#22c55e"

    message_html: str
    if message_body:
        # Escape and preserve line breaks
        escaped = (
            message_body
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br>")
        )
        message_html = f'<p style="font-family:monospace;font-size:13px;color:#d1d5db;line-height:1.7;margin:0;">{escaped}</p>'
    else:
        message_html = '<p style="font-style:italic;color:#6b7280;font-size:13px;">Not available — this action does not produce a customer message.</p>'

    channel_label = channel.upper() if channel else "—"
    fallback_label = "Fallback Used" if fallback_used else "Not Used"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>Revenue Recovery Decision Report</title>
</head>
<body style="margin:0;padding:0;background:#0a0d12;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0a0d12;padding:32px 16px;">
    <tr><td align="center">
      <table width="640" cellpadding="0" cellspacing="0" style="max-width:640px;width:100%;background:#0e1420;border:1px solid #1e2a38;border-radius:16px;overflow:hidden;">

        <!-- Header -->
        <tr>
          <td style="background:linear-gradient(135deg,#111827 0%,#0d1520 100%);padding:28px 32px;border-bottom:1px solid #1e2a38;">
            <p style="margin:0;font-size:10px;letter-spacing:3px;text-transform:uppercase;color:#e8a33d;font-weight:700;">AI Revenue Recovery Engine</p>
            <h1 style="margin:8px 0 0;font-size:22px;font-weight:800;color:#f3f4f6;letter-spacing:-0.5px;">Revenue Recovery Decision</h1>
          </td>
        </tr>

        <!-- Decision Fields -->
        <tr>
          <td style="padding:28px 32px;">
            <table width="100%" cellpadding="0" cellspacing="0">

              {"".join([
                _html_field_row(label, value, color)
                for label, value, color in [
                    ("Transaction ID",       txn_id,       None),
                    ("Amount",               amount_disp,  "#f3c06b"),
                    ("Failure Type",         failure,      None),
                    ("Recommended Action",   action,       "#e8a33d"),
                    ("Decision Type",        dec_type,     None),
                    ("Recovery Probability", prob_display, "#60a5fa"),
                    ("Expected Value",       ev_display,   "#f3c06b"),
                    ("Escalation",           escalation,   escalation_color),
                    ("Terminal",             terminal,     terminal_color),
                    ("Trace ID",             trace_id,     None),
                    ("Policy Version",       policy_ver,   None),
                ]
              ])}

            </table>
          </td>
        </tr>

        <!-- Customer Message -->
        <tr>
          <td style="padding:0 32px 28px;">
            <table width="100%" cellpadding="0" cellspacing="0"
                   style="background:#060810;border:1px solid #1b2535;border-radius:12px;overflow:hidden;">
              <tr>
                <td style="padding:14px 18px;border-bottom:1px solid #141c28;">
                  <p style="margin:0;font-size:10px;letter-spacing:2px;text-transform:uppercase;color:#9ca3af;font-weight:600;">Customer Message</p>
                  <p style="margin:4px 0 0;font-size:10px;color:#e8a33d;font-style:italic;">Included for audit purposes only — NOT sent to the customer</p>
                </td>
              </tr>
              <tr>
                <td style="padding:18px;">
                  {message_html}
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Communication Status -->
        <tr>
          <td style="padding:0 32px 28px;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td width="50%" style="padding-right:8px;">
                  <div style="background:#060810;border:1px solid #1b2535;border-radius:10px;padding:14px 16px;">
                    <p style="margin:0;font-size:10px;text-transform:uppercase;letter-spacing:1.5px;color:#6b7280;">Communication Status</p>
                    <p style="margin:6px 0 0;font-size:13px;font-weight:700;color:{comm_status_color};">{comm_status_label}</p>
                    <p style="margin:4px 0 0;font-size:12px;color:#9ca3af;">Channel: {channel_label}</p>
                  </div>
                </td>
                <td width="50%" style="padding-left:8px;">
                  <div style="background:#060810;border:1px solid #1b2535;border-radius:10px;padding:14px 16px;">
                    <p style="margin:0;font-size:10px;text-transform:uppercase;letter-spacing:1.5px;color:#6b7280;">Fallback Status</p>
                    <p style="margin:6px 0 0;font-size:13px;font-weight:700;color:#d1d5db;">{fallback_label}</p>
                  </div>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="padding:20px 32px;border-top:1px solid #1e2a38;text-align:center;">
            <p style="margin:0;font-size:11px;color:#4b5563;">
              Generated automatically by the AI Revenue Recovery Engine · Do not reply
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""

    return html


def _html_field_row(label: str, value: str, color: Optional[str]) -> str:
    val_style = f"color:{color};" if color else "color:#e5e7eb;"
    return f"""
              <tr>
                <td style="padding:8px 0;border-bottom:1px solid #141c28;">
                  <p style="margin:0;font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:1px;">{label}</p>
                  <p style="margin:3px 0 0;font-size:13px;font-weight:600;font-family:monospace;{val_style}">{value}</p>
                </td>
              </tr>"""


# ─────────────────────────────────────────────────────────────────────────────
# SMTP SENDER
# ─────────────────────────────────────────────────────────────────────────────

def send_report_email(payload: Dict[str, Any]) -> None:
    """
    Build and send the decision report email via Gmail SMTP (STARTTLS).

    Raises RuntimeError if SMTP credentials are missing or sending fails.
    """
    cfg = _smtp_config()
    if not cfg["username"] or not cfg["password"]:
        raise RuntimeError(
            "SMTP credentials not configured — "
            "set REPORT_EMAIL_USERNAME and REPORT_EMAIL_PASSWORD in .env"
        )

    txn_id = payload.get("transaction_id", "Unknown")
    action = (payload.get("selected_action") or "unknown").upper()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[Recovery Engine] Decision Report — {action} · {txn_id}"
    msg["From"]    = cfg["from"] or cfg["username"]
    msg["To"]      = cfg["username"]   # send to the configured account itself

    plain = build_plain_text(payload)
    html  = build_html(payload)

    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html,  "html",  "utf-8"))

    with smtplib.SMTP(cfg["host"], cfg["port"]) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(cfg["username"], cfg["password"])
        server.sendmail(msg["From"], [msg["To"]], msg.as_string())
