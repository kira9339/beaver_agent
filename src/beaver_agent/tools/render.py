"""Plain-text rendering of tool results.

These are byte-for-byte ports of the ``tool=True`` branches the CLI used to
print, so the model sees the same observations it was prompted against. Session
rendering had no such branch before (it always went through Rich tables), so it
is written here in the same flat style.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

SEPARATOR = "-" * 20


def _due_at(value: Any) -> str:
    if not value:
        return "none"
    try:
        return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return value[:16] if isinstance(value, str) and len(value) >= 16 else str(value)


def _short(value: Any) -> str:
    return value[:16] if isinstance(value, str) and len(value) >= 16 else str(value or "")


# --- reminders --------------------------------------------------------------

def reminder_created(reminder: Any) -> str:
    return "\n".join([
        "remind created",
        f"ID: {reminder.id}",
        f"Title: {reminder.title}",
        f"Status: {reminder.status}",
        f"Due At: {_due_at(reminder.due_at)}",
        f"Repeat: {'yes' if reminder.repeat_rule else 'no'}",
    ])


def reminder_detail(reminder: Any) -> str:
    return "\n".join([
        f"ID: {reminder.id}",
        f"Title: {reminder.title}",
        f"Body: {reminder.body or ''}",
        f"Due At: {_due_at(reminder.due_at)}",
        f"Status: {reminder.status}",
        f"Repeat: {'yes' if reminder.repeat_rule else 'no'}",
    ])


def reminders_list(reminders: List[Any]) -> str:
    if not reminders:
        return "no reminds found"
    lines = ["reminds list", "ID | Title | Status | Due At | Repeat"]
    for r in reminders:
        lines.append(
            f"{r.id} | {r.title} | {r.status} | {_due_at(r.due_at)} | "
            f"{'yes' if r.repeat_rule else 'no'}"
        )
    return "\n".join(lines)


# --- documents --------------------------------------------------------------

def document_ingested(doc: Any) -> str:
    return f"document ingested: {doc.file_name} (ID: {doc.id}), chunks: {len(doc.chunks)}"


def documents_list(docs: List[Any]) -> str:
    if not docs:
        return "no documents found"
    lines = ["documents list", "ID | File Name | Chunks | Created At"]
    for d in docs:
        chunk_count = d.metadata.get('chunks_count') if d.metadata else len(d.chunks)
        lines.append(f"{d.id} | {d.file_name} | {chunk_count} | {d.created_at or ''}")
    return "\n".join(lines)


def document_detail(doc: Any, full: bool = False) -> str:
    preview_items = [c.get("content") for c in doc.chunks]
    if not full:
        preview_items = preview_items[:3]
    preview_text = "\n".join([f"chunk{i + 1}:\n{chunk}" for i, chunk in enumerate(preview_items)])
    return "\n".join([
        f"document ID: {doc.id}",
        f"file name: {doc.file_name}",
        f"chunks: {len(doc.chunks)}",
        "preview:",
        preview_text or "none",
    ])


def document_deleted(doc_id: str, success: bool) -> str:
    if success:
        return f"document {doc_id} deleted successfully"
    return f"delete failed: document {doc_id} not found or no permission"


def search_results(results: List[Any], k: int, full: bool = True) -> str:
    if not results:
        return "no document chunks found"
    lines = [f"search results (Top-{k}):"]
    for i, r in enumerate(results, 1):
        content = r.text
        if not full and len(content) > 200:
            content = content[:200] + "..."
        lines.append(f"[{i}] {r.file_name} (Chunk ID: {r.chunk_id})")
        lines.append(f"page index: {r.page_idx}")
        lines.append(f"similarity score: {r.score:.4f}")
        lines.append(f"content: {content}")
        lines.append(SEPARATOR)
    return "\n".join(lines)


# --- preferences ------------------------------------------------------------

def preference_added(pref: Any) -> str:
    return "\n".join([
        "preference added successfully",
        f"content: {pref.text}",
        f"confidential: {'yes' if pref.confidential else 'no'}",
        f"ID: {pref.id}",
        f"created at: {pref.created_at or 'unknown'}",
    ])


def preferences_list(preferences: List[Any]) -> str:
    if not preferences:
        return "no preference found"
    lines = ["preference list", "ID | content | confidential | created at"]
    for p in preferences:
        lines.append(
            f"{p.id} | {p.text} | {'yes' if p.confidential else 'no'} | {_short(p.created_at)}"
        )
    return "\n".join(lines)


def merge_result(result: Dict[str, Any], username: str) -> str:
    lines = [result['message']]
    if result["merged_count"] > 0:
        lines.append(f"merged count: {result['merged_count']}")
        lines.append(f"remaining count: {result['remaining_count']}")
        lines.append(f"username: {username}")
    return "\n".join(lines)


def preference_delete_confirm(pref: Any) -> str:
    return "\n".join([
        "preference to delete:",
        f"ID: {pref.id}",
        f"content: {pref.text}",
        f"confidential: {'yes' if pref.confidential else 'no'}",
        f"created at: {pref.created_at or 'unknown'}",
    ])


# --- notes ------------------------------------------------------------------

def _tags(note: Any) -> str:
    return ",".join(note.tags) if getattr(note, "tags", None) else "none"


def note_created(note: Any) -> str:
    return "\n".join([
        "note created:",
        f"ID: {note.id}",
        f"title: {note.title}",
        f"tags: {_tags(note)}",
    ])


def note_updated(note: Any) -> str:
    return "\n".join([
        "note updated:",
        f"ID: {note.id}",
        f"title: {note.title}",
        f"tags: {_tags(note)}",
    ])


def notes_list(notes: List[Any]) -> str:
    if not notes:
        return "no note found"
    lines = ['note list', 'ID | title | tags | created at | updated at']
    for n in notes:
        lines.append(
            f"{n.id} | {n.title} | {_tags(n)} | {_short(n.created_at)} | {_short(n.updated_at)}"
        )
    return "\n".join(lines)


def note_detail(note: Any) -> str:
    return "\n".join([
        f"ID: {note.id}",
        f"title: {note.title}",
        f"content: {note.content}",
        f"tags: {_tags(note)}",
        f"created at: {_short(note.created_at)} | updated at: {_short(note.updated_at)}",
    ])


def note_search_results(notes: List[Any]) -> str:
    if not notes:
        return "no note searched"
    lines = ["search results", "ID | title | tags | created at"]
    for n in notes:
        lines.append(f"{n.id} | {n.title} | {_tags(n)} | {_short(getattr(n, 'created_at', None))}")
    return "\n".join(lines)


# --- sessions ---------------------------------------------------------------

def conversations_list(conversations: List[Any], username: str) -> str:
    if not conversations:
        return "no session found"
    lines = [f"conversation list (user: {username})",
             "ID | title | turns | mode | updated at"]
    for conv in conversations:
        mode = (conv.metadata or {}).get("mode", "/")
        # The CLI reported turn count, i.e. half the raw message count.
        lines.append(
            f"{conv.id} | {conv.title} | {conv.message_count // 2} | {mode} | {_short(conv.updated_at)}"
        )
    return "\n".join(lines)


def session_detail(conversation: Any) -> str:
    return "\n".join([
        f"ID: {conversation.id}",
        f"title: {conversation.title}",
        f"message count: {conversation.message_count}",
        f"created at: {conversation.created_at}",
        f"updated at: {conversation.updated_at}",
    ])


def session_messages(messages: List[Any], limit: int = 20) -> str:
    if not messages:
        return "no messages in this conversation"
    recent = messages[-limit:]
    lines = [f"session messages (showing last {len(recent)} of {len(messages)}):"]
    for m in recent:
        role = m.role if isinstance(m.role, str) else str(getattr(m.role, "value", m.role))
        if role == "assistant":
            tcs = (getattr(m, "metadata", None) or {}).get("tool_calls") or []
            names = [((tc.get("function") or {}).get("name")) for tc in tcs if isinstance(tc, dict)]
            names = [n for n in names if n]
            if names:
                lines.append(f"assistant [tool calls: {', '.join(names)}]:")
        elif role == "tool":
            name = (getattr(m, "metadata", None) or {}).get("name") or ""
            lines.append(f"tool{(': ' + name) if name else ''}: {m.content}")
            continue
        else:
            lines.append(f"{role}:")
        lines.append(m.content)
        lines.append(SEPARATOR)
    return "\n".join(lines)


def session_deleted(title: str, session_id: str) -> str:
    return f"session '{title}' ({session_id[:8]}...) deleted successfully"
