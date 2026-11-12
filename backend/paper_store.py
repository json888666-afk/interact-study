import json
import re
import unicodedata
from uuid import uuid4

def initialize_papers(connection):
    connection.execute("""CREATE TABLE IF NOT EXISTS imported_papers (
        id TEXT PRIMARY KEY,
        account_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        exam TEXT NOT NULL, exam_key TEXT NOT NULL,
        subject TEXT NOT NULL, subject_key TEXT NOT NULL,
        year INTEGER, paper TEXT, filenames TEXT NOT NULL,
        fingerprint TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(account_id, exam_key, subject_key, fingerprint)
    )""")
    connection.execute("""CREATE TABLE IF NOT EXISTS imported_questions (
        id INTEGER PRIMARY KEY, paper_id TEXT NOT NULL REFERENCES imported_papers(id) ON DELETE CASCADE,
        data TEXT NOT NULL, searchable TEXT NOT NULL, ready INTEGER NOT NULL,
        confirmed INTEGER NOT NULL DEFAULT 0
    )""")
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(imported_questions)")}
    if "confirmed" not in columns:
        connection.execute("ALTER TABLE imported_questions ADD COLUMN confirmed INTEGER NOT NULL DEFAULT 0")
    connection.execute("CREATE INDEX IF NOT EXISTS imported_questions_by_paper ON imported_questions(paper_id)")
    connection.execute("CREATE VIRTUAL TABLE IF NOT EXISTS imported_question_search USING fts5(searchable)")
    connection.execute("""CREATE TRIGGER IF NOT EXISTS imported_question_search_insert
        AFTER INSERT ON imported_questions BEGIN
        INSERT INTO imported_question_search(rowid, searchable) VALUES (new.id, new.searchable);
    END""")
    connection.execute("""CREATE TRIGGER IF NOT EXISTS imported_question_search_delete
        AFTER DELETE ON imported_questions BEGIN
        DELETE FROM imported_question_search WHERE rowid = old.id;
    END""")
    connection.execute("""CREATE TRIGGER IF NOT EXISTS imported_question_search_update
        AFTER UPDATE OF searchable ON imported_questions BEGIN
        DELETE FROM imported_question_search WHERE rowid = old.id;
        INSERT INTO imported_question_search(rowid, searchable) VALUES (new.id, new.searchable);
    END""")
    merge_duplicate_papers(connection)


def compact(value):
    return re.sub(r"[^\w]", "", unicodedata.normalize("NFKC", value).casefold())


def exam_key(exam, subject):
    exam_without_year = re.sub(r"(?<!\d)(?:19|20)\d{2}(?!\d)\s*年?", "", exam)
    key = compact(exam_without_year).replace(compact(subject), "")
    return re.sub(r"市(?=中考|高考)", "", key) or compact(exam)


def tokens(text):
    value = unicodedata.normalize("NFKC", text).casefold()
    found = []
    for part in re.findall(r"[a-z0-9]+|[\u3400-\u9fff]+", value):
        if part.isascii() or len(part) <= 2:
            found.append(part)
        else:
            found.extend(part[i:i + n] for n in (3, 2) for i in range(len(part) - n + 1))
    return list(dict.fromkeys(found))


def matching_questions(connection, account_id, text, target=None, *, limit=20):
    words = tokens(text)[:60]
    if not account_id or not words:
        return []
    query = " OR ".join(f'"{word}"' for word in words)
    filters = ""
    args = [query, account_id]
    if target:
        filters = " AND p.exam_key = ? AND p.subject_key = ?"
        args += [exam_key(target.exam, target.subject), compact(target.subject)]
    return connection.execute("""SELECT q.data, p.exam, p.subject, p.year, p.paper, p.filenames
        FROM imported_question_search s
        JOIN imported_questions q ON q.id = s.rowid
        JOIN imported_papers p ON p.id = q.paper_id
        WHERE imported_question_search MATCH ? AND p.account_id = ? AND q.confirmed = 1"""
        + filters + " ORDER BY bm25(imported_question_search), q.id DESC LIMIT ?", (*args, limit)).fetchall()


def question_identity(section, number):
    number = unicodedata.normalize("NFKC", number).strip()
    section = compact(section or "")
    if match := re.fullmatch(r"(?:([A-Za-z甲乙丙丁]\s*卷)\s*)?(?:第\s*)?(\d{1,3})\s*[.、题]?", number):
        return section or compact(match[1] or ""), str(int(match[2]))
    return section, number


def number_order(number):
    return (0, int(number)) if number.isdecimal() else (1, number)


def status(item):
    if not item.get("confirmed"):
        return "draft"
    return "ready" if item.get("ready") else "review_only"


def rank(item):
    if not item.get("confirmed"):
        return 0
    return 2 if item.get("ready") else 1


def question_rows(connection, paper_id):
    return [(row["id"], json.loads(row["data"]) | {"confirmed": bool(row["confirmed"])})
            for row in connection.execute(
                "SELECT id, data, confirmed FROM imported_questions WHERE paper_id = ? ORDER BY id", (paper_id,),
            )]


def get_question(connection, paper_id, question_id):
    row = connection.execute("SELECT data, confirmed FROM imported_questions WHERE paper_id = ? AND id = ?",
                             (paper_id, question_id)).fetchone()
    return (json.loads(row["data"]) | {"confirmed": bool(row["confirmed"])}) if row else None


def write_question(connection, paper_id, item, question_id=None):
    terms = " ".join(tokens(" ".join([item["stem"], *item["tags"]])))
    values = (json.dumps(item, ensure_ascii=False), terms, int(item["ready"]),
              int(item.get("confirmed", False)), paper_id)
    if question_id is None:
        return connection.execute(
            "INSERT INTO imported_questions (data, searchable, ready, confirmed, paper_id) VALUES (?, ?, ?, ?, ?)",
            values,
        ).lastrowid
    connection.execute(
        "UPDATE imported_questions SET data = ?, searchable = ?, ready = ?, confirmed = ? WHERE paper_id = ? AND id = ?",
        (*values, question_id))
    return question_id


def merge_questions(connection, paper_id, questions):
    index, incoming = {}, {}
    for question_id, item in question_rows(connection, paper_id):
        section, number = question_identity(item.get("section"), item["number"])
        index.setdefault((item["file"], item["page"], number), {})[section] = (question_id, item)
    for item in questions:
        section, number = question_identity(item.get("section"), item["number"])
        if section:
            incoming.setdefault((item["file"], item["page"], number), set()).add(section)
    for item in questions:
        section, number = question_identity(item.get("section"), item["number"])
        key = item["file"], item["page"], number
        siblings = index.setdefault(key, {})
        match = section if section in siblings else None
        if match is None:
            if not section and len(siblings) == 1:
                match = next(iter(siblings))
            elif section and "" in siblings and (len(incoming[key]) == 1 or
                    bool(item["stem"] and item["stem"] == siblings[""][1]["stem"])):
                match = ""
        if match is None:
            if section or len(siblings) <= 1:
                siblings[section] = (write_question(connection, paper_id, item), item)
            continue
        question_id, old = siblings[match]
        # 重新识别只产生草稿：已确认的题优先保留，草稿之间以新结果为准。
        keep = item if rank(item) > rank(old) or (rank(item) == 0 and rank(old) == 0) else old
        updated = keep | {"section": item.get("section") or old.get("section") or match or None, "number": number,
                          "section_order": item.get("section_order", old.get("section_order", 0))}
        if updated != old:
            write_question(connection, paper_id, updated, question_id)
        siblings.pop(match)
        siblings[section or match] = question_id, updated


def find_duplicate(connection, account_id, metadata, fingerprint):
    return connection.execute("""SELECT id FROM imported_papers
        WHERE account_id = ? AND exam_key = ? AND subject_key = ? AND fingerprint = ?""",
        (account_id, exam_key(metadata.exam, metadata.subject), compact(metadata.subject), fingerprint)).fetchone()


def find_exam_paper(connection, account_id, exam, subject):
    return connection.execute("""SELECT id, filenames FROM imported_papers
        WHERE account_id = ? AND exam_key = ? AND subject_key = ?
        ORDER BY created_at, rowid LIMIT 1""",
        (account_id, exam_key(exam, subject), compact(subject))).fetchone()


def add_filenames(connection, paper_id, filenames):
    row = connection.execute("SELECT filenames FROM imported_papers WHERE id = ?", (paper_id,)).fetchone()
    if not row:
        return
    current = json.loads(row["filenames"])
    for name in filenames:
        if name not in current:
            current.append(name)
    connection.execute("UPDATE imported_papers SET filenames = ? WHERE id = ?", (json.dumps(current), paper_id))


def save_paper(connection, account_id, metadata, filenames, fingerprint, questions):
    if existing := find_duplicate(connection, account_id, metadata, fingerprint):
        return existing["id"], True, False
    if target := find_exam_paper(connection, account_id, metadata.exam, metadata.subject):
        merge_questions(connection, target["id"], questions)
        add_filenames(connection, target["id"], filenames)
        return target["id"], False, True
    paper_id = str(uuid4())
    connection.execute("""INSERT INTO imported_papers
        (id, account_id, exam, exam_key, subject, subject_key, year, paper, filenames, fingerprint)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
        paper_id, account_id, metadata.exam, exam_key(metadata.exam, metadata.subject),
        metadata.subject, compact(metadata.subject), metadata.year, metadata.paper, json.dumps(filenames), fingerprint,
    ))
    merge_questions(connection, paper_id, questions)
    return paper_id, False, False


def merge_duplicate_papers(connection):
    groups = connection.execute("""SELECT account_id, exam_key, subject_key
        FROM imported_papers GROUP BY account_id, exam_key, subject_key HAVING COUNT(*) > 1""").fetchall()
    for group in groups:
        papers = connection.execute("""SELECT id, filenames FROM imported_papers
            WHERE account_id = ? AND exam_key = ? AND subject_key = ?
            ORDER BY created_at, rowid""", (group["account_id"], group["exam_key"], group["subject_key"])).fetchall()
        target, duplicates = papers[0], papers[1:]
        names = []
        for duplicate in duplicates:
            names.extend(json.loads(duplicate["filenames"]))
            merge_questions(connection, target["id"],
                            [data for _, data in question_rows(connection, duplicate["id"])])
        add_filenames(connection, target["id"], names)
        for duplicate in duplicates:
            connection.execute("DELETE FROM imported_papers WHERE id = ?", (duplicate["id"],))


PAPER_SUMMARY = """SELECT p.id, p.exam, p.subject, p.year, p.paper, p.filenames, p.created_at,
    COUNT(q.id) AS question_count,
    COALESCE(SUM(q.confirmed = 0), 0) AS draft_count,
    COALESCE(SUM(q.confirmed = 1 AND q.ready = 1), 0) AS ready_count,
    COALESCE(SUM(q.confirmed = 1 AND q.ready = 0), 0) AS review_count
    FROM imported_papers p LEFT JOIN imported_questions q ON q.paper_id = p.id"""


def paper_summary(row):
    summary = dict(row)
    return summary | {"filenames": json.loads(row["filenames"]),
                      "confirmed_count": summary["ready_count"] + summary["review_count"]}


def list_papers(connection, account_id):
    return [paper_summary(row) for row in connection.execute(
        PAPER_SUMMARY + " WHERE p.account_id = ? GROUP BY p.id ORDER BY p.created_at DESC, p.rowid DESC LIMIT 100",
        (account_id,),
    )]


def get_paper(connection, account_id, paper_id):
    row = connection.execute(PAPER_SUMMARY + " WHERE p.account_id = ? AND p.id = ? GROUP BY p.id",
                             (account_id, paper_id)).fetchone()
    if not row:
        return None
    filenames = json.loads(row["filenames"])
    file_order = {name: index for index, name in enumerate(filenames)}
    questions = question_rows(connection, paper_id)
    section_order = {}
    for _, item in questions:
        section, _ = question_identity(item.get("section"), item["number"])
        section_order.setdefault((item["file"], item["page"], section), len(section_order))

    def order(row):
        _, item = row
        section, number = question_identity(item.get("section"), item["number"])
        section_position = item.get("section_order", section_order[item["file"], item["page"], section])
        return file_order.get(item["file"], len(filenames)), item["page"], section_position, number_order(number)

    return paper_summary(row) | {"questions": [
        {key: item[key] for key in ("number", "stem", "options", "correct", "kind", "tags", "ready", "file", "page")}
        | {"id": question_id, "section": item.get("section"), "confirmed": item.get("confirmed", False),
           "status": status(item), "reason": item.get("reason", "")}
        for question_id, item in sorted(questions, key=order)
    ]}
