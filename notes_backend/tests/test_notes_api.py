def _create_note(client, title="T1", content="C1", tags=None, pinned=False, starred=False):
    payload = {
        "title": title,
        "content": content,
        "tags": tags or [],
        "pinned": pinned,
        "starred": starred,
    }
    r = client.post("/notes", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["id"] > 0
    assert body["title"] == title
    assert body["content"] == content
    assert body["pinned"] == pinned
    assert body["starred"] == starred
    # API normalizes tags to lower/trim/unique and returns sorted.
    if tags is not None:
        assert sorted(set([t.strip().lower() for t in tags if t and t.strip()])) == body["tags"]
    return body


def test_create_get_update_delete_note_crud(client):
    created = _create_note(client, title="Hello", content="World", tags=["Work", "work", "  "], pinned=True)

    # Get
    r = client.get(f"/notes/{created['id']}")
    assert r.status_code == 200
    got = r.json()
    assert got["id"] == created["id"]
    assert got["title"] == "Hello"
    assert got["tags"] == ["work"]
    assert got["pinned"] is True

    # Patch: change title + replace tags + starred
    r = client.patch(
        f"/notes/{created['id']}",
        json={"title": "Hello2", "tags": ["Personal", "work"], "starred": True},
    )
    assert r.status_code == 200
    updated = r.json()
    assert updated["title"] == "Hello2"
    # tags are normalized + sorted by name in output
    assert updated["tags"] == ["personal", "work"]
    assert updated["starred"] is True

    # Delete
    r = client.delete(f"/notes/{created['id']}")
    assert r.status_code == 200
    assert r.json() == {"deleted": True, "id": created["id"]}

    # Get after delete -> 404
    r = client.get(f"/notes/{created['id']}")
    assert r.status_code == 404
    assert "not found" in r.json()["detail"].lower()


def test_list_notes_empty(client):
    r = client.get("/notes")
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 0


def test_list_notes_search_tag_and_multi_tags_and_starred(client):
    n1 = _create_note(client, title="Alpha", content="first note", tags=["work"], starred=True)
    n2 = _create_note(client, title="Beta", content="second note", tags=["work", "personal"])
    _ = _create_note(client, title="Gamma", content="third note", tags=["personal"])

    # q search matches title/content (case-insensitive)
    r = client.get("/notes", params={"q": "ALP"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert [it["id"] for it in body["items"]] == [n1["id"]]

    # single tag filter
    r = client.get("/notes", params={"tag": "work"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    got_ids = sorted([it["id"] for it in body["items"]])
    assert got_ids == sorted([n1["id"], n2["id"]])

    # multi tags AND semantics
    r = client.get("/notes", params={"tags": "work,personal"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert [it["id"] for it in body["items"]] == [n2["id"]]

    # starred filter
    r = client.get("/notes", params={"starred": "true"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert [it["id"] for it in body["items"]] == [n1["id"]]


def test_update_nonexistent_note_returns_404(client):
    r = client.patch("/notes/999999", json={"title": "x"})
    assert r.status_code == 404
    assert "not found" in r.json()["detail"].lower()


def test_delete_nonexistent_note_returns_404(client):
    r = client.delete("/notes/999999")
    assert r.status_code == 404
    assert "not found" in r.json()["detail"].lower()
