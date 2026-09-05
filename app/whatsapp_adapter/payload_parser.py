"""
Webhook payload parsing.

The WhatsApp Cloud API webhook JSON is deeply nested and can contain
multiple entries/changes/messages per request, plus status updates
(delivered/read receipts) that aren't user messages at all. This
module's job is purely to extract "is there a real user message
here, and if so what kind" — see Meta's webhook payload reference:
https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/components
"""
from dataclasses import dataclass


@dataclass
class IncomingMessage:
    from_phone: str
    message_type: str  # "text" | "audio" | "document" | "image" | "unsupported"
    text: str | None = None
    media_id: str | None = None
    filename: str | None = None  # for document messages


def extract_messages(payload: dict) -> list[IncomingMessage]:
    messages: list[IncomingMessage] = []

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for msg in value.get("messages", []):
                from_phone = msg.get("from", "")
                msg_type = msg.get("type", "unsupported")

                if msg_type == "text":
                    messages.append(
                        IncomingMessage(
                            from_phone=from_phone,
                            message_type="text",
                            text=msg.get("text", {}).get("body", ""),
                        )
                    )
                elif msg_type == "audio":
                    messages.append(
                        IncomingMessage(
                            from_phone=from_phone,
                            message_type="audio",
                            media_id=msg.get("audio", {}).get("id"),
                        )
                    )
                elif msg_type == "document":
                    doc = msg.get("document", {})
                    messages.append(
                        IncomingMessage(
                            from_phone=from_phone,
                            message_type="document",
                            media_id=doc.get("id"),
                            filename=doc.get("filename", "document"),
                        )
                    )
                # image/video/location/etc: not in this project's
                # scope yet — silently skip rather than error, since
                # status updates and other change types share this
                # same payload shape and are expected to be ignored.

    return messages
