def _create_note(client, title, tags=None):
    r = client.post(
        "/notes",
        json={"title": title, "content": f"content {title}", "tags": tags or [], "pinned": False, "starred": False},
    )
    assert r.status_code == 200
    return r.json()


def test_bulk_delete_notes_returns_deleted_and_not_found(client):
    n1 = _create_note(client, "n1")
    n2 = _create_note(client, "n2")

    r = client.post("/notes/bulk/delete", json={"note_ids": [n1["id"], 999999, n2["id"]]})
    assert r.status_code == 200
    body = r.json()
    assert body["deleted_ids"] == sorted([n1["id"], n2["id"]])
    assert body["not_found_ids"] == [999999]

    # Ensure they are actually gone
    r = client.get("/notes")
    assert r.status_code == 200
    assert r.json()["total"] == 0


def test_bulk_add_and_remove_tags_are_idempotent(client):
    n1 = _create_note(client, "n1", tags=["work"])
    n2 = _create_note(client, "n2", tags=[])

    # Add tags to both, plus a non-existent note id
    r = client.post("/notes/bulk/tags/add", json={"note_ids": [n1["id"], n2["id"], 1234567], "tags": ["Work", "New"]})
    assert r.status_code == 200
    body = r.json()
    assert body["updated_ids"] == sorted([n1["id"], n2["id"]])
    assert body["not_found_ids"] == [1234567]

    # Verify tags were added (normalized/sorted)
    r1 = client.get(f"/notes/{n1['id']}")
    assert r1.status_code == 200
    assert r1.json()["tags"] == ["new", "work"]

    r2 = client.get(f"/notes/{n2['id']}")
    assert r2.status_code == 200
    assert r2.json()["tags"] == ["new", "work"]

    # Remove one tag from both (idempotent even if repeated)
    r = client.post("/notes/bulk/tags/remove", json={"note_ids": [n1["id"], n2["id"]], "tags": ["new"]})
    assert r.status_code == 200
    body = r.json()
    assert body["updated_ids"] == sorted([n1["id"], n2["id"]])
    assert body["not_found_ids"] == []

    r = client.post("/notes/bulk/tags/remove", json={"note_ids": [n1["id"], n2["id"]], "tags": ["new"]})
    assert r.status_code == 200

    # Verify remaining tags
    assert client.get(f"/notes/{n1['id']}").json()["tags"] == ["work"]
    assert client.get(f"/notes/{n2['id']}").json()["tags"] == ["work"]
