from ui import route_text


def test_route_text_allows_todo_without_args():
    r = route_text("/todo")
    assert r["kind"] == "command"
    assert r["command"] == "todo"
    # for /todo, args can be empty; wizard will drive next steps
    assert (r.get("text") or "") == ""
