"""Email agent — natural language over Gmail + Outlook (4 accounts).

The model picks the right tool. Sends are restricted to the main Gmail
and school Outlook accounts; spam Gmails are read/triage-only.
"""

from __future__ import annotations

from typing import Any

from brainbot.agents.base import BaseAgent
from brainbot.config import get_settings
from brainbot.connectors import gmail, outlook
from brainbot.llm.tools import (
    Tool,
    schema_array,
    schema_object,
    schema_string,
)


class EmailAgent(BaseAgent):
    name = "email"
    smart = False
    system_prompt = (
        "You are the Email agent. The user has four mail accounts:\n"
        " - 'main' (Gmail, read+send)\n"
        " - 'spam1' (Gmail, READ-ONLY)\n"
        " - 'spam2' (Gmail, READ-ONLY)\n"
        " - 'school' (Outlook via Microsoft Graph, read+send)\n"
        "When asked to act 'across all inboxes', loop the read tools across all four labels.\n"
        "Before sending an email, summarise what you're about to send and ask 'send now?'.\n"
        "Be concise. Use Markdown bullets for lists."
    )

    def register_tools(self) -> None:
        labels = list(get_settings().google_account_label_list) + [get_settings().ms_account_label]

        self.tools.add(Tool(
            name="list_emails",
            description="List recent emails from one account. Default query: unread.",
            parameters=schema_object(
                {
                    "account": schema_string("Account label.", enum=labels),
                    "query": schema_string(
                        "Gmail search query (e.g. 'is:unread', 'from:boss'). "
                        "For Outlook, use 'isRead eq false' style $filter.",
                    ),
                    "max_results": {"type": "integer", "description": "Default 20."},
                },
                required=["account"],
            ),
            handler=_list_emails,
        ))

        self.tools.add(Tool(
            name="read_email",
            description="Fetch the full body of a specific email by id.",
            parameters=schema_object(
                {
                    "account": schema_string("Account label.", enum=labels),
                    "message_id": schema_string("Provider-specific message id."),
                },
                required=["account", "message_id"],
            ),
            handler=_read_email,
        ))

        self.tools.add(Tool(
            name="send_email",
            description="Send a new email. Only valid on 'main' and 'school'.",
            parameters=schema_object(
                {
                    "account": schema_string("'main' or 'school'.", enum=["main", "school"]),
                    "to": schema_string("Recipient address."),
                    "subject": schema_string("Subject line."),
                    "body": schema_string("Plain-text body."),
                    "reply_to_message_id": schema_string(
                        "Optional. If replying, the message id to thread under."
                    ),
                },
                required=["account", "to", "subject", "body"],
            ),
            handler=_send_email,
        ))

        self.tools.add(Tool(
            name="delete_email",
            description="Move an email to trash (Gmail) or delete it (Outlook).",
            parameters=schema_object(
                {
                    "account": schema_string("Account label.", enum=labels),
                    "message_id": schema_string("Message id to delete."),
                },
                required=["account", "message_id"],
            ),
            handler=_delete_email,
        ))

        self.tools.add(Tool(
            name="label_email",
            description="Add or remove Gmail labels on a message (Gmail accounts only).",
            parameters=schema_object(
                {
                    "account": schema_string("Gmail account label.", enum=labels),
                    "message_id": schema_string("Gmail message id."),
                    "add": schema_array(schema_string("Label id."), "Labels to add."),
                    "remove": schema_array(schema_string("Label id."), "Labels to remove."),
                },
                required=["account", "message_id"],
            ),
            handler=_label_email,
        ))


# ── Tool handlers ──────────────────────────────────────────────────────

async def _list_emails(args: dict[str, Any]) -> list[dict[str, Any]]:
    account = args["account"]
    if account == get_settings().ms_account_label:
        out = await outlook.list_messages(
            query=args.get("query") or "isRead eq false",
            top=int(args.get("max_results", 20)),
        )
        return [vars(m) for m in out]
    out = await gmail.list_messages(
        account, query=args.get("query") or "is:unread", max_results=int(args.get("max_results", 20))
    )
    return [vars(m) for m in out]


async def _read_email(args: dict[str, Any]) -> dict[str, Any]:
    account = args["account"]
    if account == get_settings().ms_account_label:
        return await outlook.get_message(args["message_id"])
    return await gmail.get_message(account, args["message_id"])


async def _send_email(args: dict[str, Any]) -> dict[str, str]:
    account = args["account"]
    if account == "school":
        await outlook.send_mail(
            to=args["to"], subject=args["subject"], body=args["body"]
        )
        return {"status": "sent", "via": "outlook"}
    mid = await gmail.send_message(
        account,
        to=args["to"],
        subject=args["subject"],
        body=args["body"],
        reply_to_message_id=args.get("reply_to_message_id"),
    )
    return {"status": "sent", "via": "gmail", "message_id": mid}


async def _delete_email(args: dict[str, Any]) -> dict[str, str]:
    account = args["account"]
    if account == get_settings().ms_account_label:
        await outlook.delete_message(args["message_id"])
    else:
        await gmail.delete_message(account, args["message_id"])
    return {"status": "deleted"}


async def _label_email(args: dict[str, Any]) -> dict[str, str]:
    account = args["account"]
    if account == get_settings().ms_account_label:
        return {"status": "skipped", "reason": "labels only supported on Gmail"}
    await gmail.modify_labels(
        account, args["message_id"], add=args.get("add"), remove=args.get("remove")
    )
    return {"status": "labelled"}
