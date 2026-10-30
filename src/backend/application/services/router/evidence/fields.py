"""Prompt lines for a record's optional fields: present values one per line, absent ones named together."""


def field_lines(fields: dict[str, str | None], record: str) -> tuple[list[str], list[str]]:
    """(`Label: value` per present field, one `Not listed in the <record>: ...` line or nothing).

    Absent fields share one line instead of one "Not specified" line each, so an answer listing a
    record's details leaves them out, while a question about one can still say the record lists none
    (rather than "I'm not sure", which is for data that wasn't retrieved).
    """
    present = [f"{label}: {value}" for label, value in fields.items() if value and value.strip()]
    absent = [label.lower() for label, value in fields.items() if not (value and value.strip())]
    return present, [f"Not listed in the {record}: {', '.join(absent)}"] if absent else []
